"""
Legalese
--------
Copyright (c) 2015, 2016 Genome Research Ltd.

Author: Colin Nolan <cn13@sanger.ac.uk>

This file is part of HGI's common Python library

This program is free software: you can redistribute it and/or modify it
under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation; either version 3 of the License, or (at
your option) any later version.

This program is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser
General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""
import glob
import logging
from abc import ABCMeta, abstractmethod
from enum import unique, Enum
from multiprocessing import Lock
from typing import Iterable, Dict, Sequence

from watchdog.events import FileSystemEventHandler, FileSystemEvent, EVENT_TYPE_DELETED, EVENT_TYPE_CREATED, \
    FileSystemMovedEvent
from watchdog.observers import Observer

from hgicommon.data_source import DataSource
from hgicommon.data_source.basic import DataSourceType
from hgicommon.mixable import Listenable


class FilesDataSource(DataSource[DataSourceType]):
    """
    Sources data from data files in a given directory.
    """
    __metaclass__ = ABCMeta

    def __init__(self, directory_location: str):
        """
        Default constructor.
        :param directory_location: the location of the directory that contains files holding data
        """
        super().__init__()
        self._directory_location = directory_location

    @abstractmethod
    def extract_data_from_file(self, file_path: str) -> Iterable[DataSourceType]:
        """
        Extracts data from the file at the given file path.
        :param file_path: the path to the file to extract data from
        :return: the extracted data
        """

    @abstractmethod
    def is_data_file(self, file_path: str) -> bool:
        """
        Determines whether the file at the given path is of interest.
        :param file_path: path to the updated file
        :return: whether the file is of interest
        """

    def get_all(self) -> Sequence[DataSourceType]:
        return FilesDataSource._extract_data_from_origin_map(self._load_all_in_directory())

    def no_error_extract_data_from_file(self, file_path: str) -> Iterable[DataSourceType]:
        """
        Proxy for `extract_data_from_file` that suppresses any errors and instead just returning an empty list.
        :param file_path: see `extract_data_from_file`
        :return: see `extract_data_from_file`
        """
        try:
            return self.extract_data_from_file(file_path)
        except Exception as e:
            logging.warning(e)
            return []

    def _load_all_in_directory(self) -> Dict[str, Iterable[DataSourceType]]:
        """
        Loads all of the data from the files in directory location.
        :return: a origin map of all the loaded data
        """
        origin_mapped_data = dict()    # type: Dict[str, Iterable[DataSourceType]]
        for file_path in glob.iglob("%s/**/*" % self._directory_location, recursive=True):
            if self.is_data_file(file_path):
                origin_mapped_data[file_path] = self.no_error_extract_data_from_file(file_path)
        return origin_mapped_data

    @staticmethod
    def _extract_data_from_origin_map(origin_mapped_data: Dict[str, Iterable[DataSourceType]]) \
            -> Iterable[DataSourceType]:
        """
        Extracts the data from a data origin map.
        :param origin_mapped_data: a map containing the origin of the data as the key string and the data as the value
        :return: the data contained within the map
        """
        data = []
        for _, data_item in origin_mapped_data.items():
            data.extend(data_item)
        return data


@unique
class FileSystemChange(Enum):
    """
    Change state of file in file system.
    """
    MODIFY = 1
    CREATE = 2
    DELETE = 3


# TODO: signature should be:
# class SynchronisedFilesDataSource(FilesDataSource[DataSourceType], Listenable[FileSystemChange]):
# However, Python's current implementation of generics does not like this (subclasses need to give to types as generic
# parameters opposed to one.
class SynchronisedFilesDataSource(FilesDataSource, Listenable[FileSystemChange]):
    """
    Synchronises data from data files in a given directory. When the data changes, the data known about at the source is
    changed. Does not have to read the data on every call to `get_all`.

    Can have listeners which are called when an update to the data is made.
    """
    __metaclass__ = ABCMeta

    def __init__(self, directory_location: str):
        """
        Default constructor.
        :param directory_location: the location of the directory that contains files holding data
        """
        super().__init__(directory_location)
        self._status_lock = Lock()
        self._running = False
        self._observer = None
        self._origin_mapped_data = dict()   # type: Dict[str, DataSourceType]

        self._event_handler = FileSystemEventHandler()
        self._event_handler.on_created = self._on_file_created
        self._event_handler.on_modified = self._on_file_modified
        self._event_handler.on_deleted = self._on_file_deleted
        self._event_handler.on_moved = self._on_file_moved
        self._event_handler.on_any_event = SynchronisedFilesDataSource._on_any_event

    def get_all(self) -> Sequence[DataSourceType]:
        if not self._running:
            raise RuntimeError("Not started")

        return FilesDataSource._extract_data_from_origin_map(self._origin_mapped_data)

    def start(self):
        """
        Monitors data kept in files in the predefined directory in a new thread.

        Note: Due to the underlying library, it may take a few milliseconds after this method is started for changes to
        start to being noticed.
        """
        with self._status_lock:
            if self._running:
                raise RuntimeError("Already running")
            self._running = True

        # Cannot re-use Observer after stopped
        self._observer = Observer()
        self._observer.schedule(self._event_handler, self._directory_location, recursive=True)
        self._observer.start()

        # Load all in directory afterwards to ensure no undetected changes between loading all and observing
        self._origin_mapped_data = self._load_all_in_directory()

    def stop(self):
        """
        Stops monitoring the predefined directory.
        """
        with self._status_lock:
            if self._running:
                assert self._observer is not None
                self._observer.stop()
                self._running = False
                self._origin_mapped_data = dict()

    def _on_file_created(self, event: FileSystemEvent):
        """
        Called when a file in the monitored directory has been created.
        :param event: the file system event
        """
        if not event.is_directory and self.is_data_file(event.src_path):
            assert event.src_path not in self._origin_mapped_data
            self._origin_mapped_data[event.src_path] = self.no_error_extract_data_from_file(event.src_path)
            self.notify_listeners(FileSystemChange.CREATE)

    def _on_file_modified(self, event: FileSystemEvent):
        """
        Called when a file in the monitored directory has been modified.
        :param event: the file system event
        """
        if not event.is_directory and self.is_data_file(event.src_path):
            assert event.src_path in self._origin_mapped_data
            self._origin_mapped_data[event.src_path] = self.no_error_extract_data_from_file(event.src_path)
            self.notify_listeners(FileSystemChange.MODIFY)

    def _on_file_deleted(self, event: FileSystemEvent):
        """
        Called when a file in the monitored directory has been deleted.
        :param event: the file system event
        """
        if not event.is_directory and self.is_data_file(event.src_path):
            assert event.src_path in self._origin_mapped_data
            del(self._origin_mapped_data[event.src_path])
            self.notify_listeners(FileSystemChange.DELETE)

    def _on_file_moved(self, event: FileSystemMovedEvent):
        """
        Called when a file in the monitored directory has been moved.

        Breaks move down into a delete and a create (which it is sometimes detected as!).
        :param event: the file system event
        """
        if not event.is_directory and self.is_data_file(event.src_path):
            delete_event = FileSystemEvent(event.src_path)
            delete_event.event_type = EVENT_TYPE_DELETED
            self._on_file_deleted(delete_event)

            create_event = FileSystemEvent(event.dest_path)
            create_event.event_type = EVENT_TYPE_CREATED
            self._on_file_created(create_event)

    @staticmethod
    def _on_any_event(event: FileSystemEvent):
        """
        Called when any file system event was detected
        :param event: the detected event
        """
        logging.debug("File system monitor has detected the event: %s" % event)
