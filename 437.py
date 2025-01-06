# -*- coding: utf-8 -*-
'''
Contains the necessary information to create an attributes for the MFT.

An MFT entry is composed of multiple attributes. Each attribute, is composed
by a header and a content. Also a attribute can be resident, when the content
is in the MFT itself or non-resident if the content is outside. If we are not
considering the content, the only difference is the information present in the
header.

As such, we have a basic attribute header (``BaseAttributeHeader``) that holds
the common attributes for the headers and specific classes that represent
the different headers.

For the content, each content has a very specific mode of be interpreted.
The implementations can also be found in this modules. One major difference
for content to the headers is that the class creation for content is
dynamic, that means that expected methods are created when the module is
imported.

Note:
    All creation code from binary stream expects a `memoryview` object. This is
    for performance reasons, as this don't generate new objects when we slice
    the data.

Important:
    The implementation of __len__ in the classes here is meant to return the
    size in BYTES, unless otherwise mentioned.

.. moduleauthor:: Júlio Dantas <jldantas@gmail.com>
'''
import struct
import logging
from operator import getitem as _getitem
from uuid import UUID
from abc import ABCMeta, abstractmethod
from math import ceil as _ceil
import sys as _sys

from libmft.util.functions import convert_filetime, get_file_reference
from libmft.flagsandtypes import AttrTypes, AttrFlags, NameType, FileInfoFlags, \
    IndexEntryFlags, VolumeFlags, ReparseType, ReparseFlags, CollationRule, \
    SecurityDescriptorFlags, ACEType, ACEControlFlags, ACEAccessFlags, \
    SymbolicLinkFlags, EAFlags
from libmft.exceptions import HeaderError, ContentError

#******************************************************************************
# MODULE LEVEL VARIABLES
#******************************************************************************

_MOD_LOGGER = logging.getLogger(__name__)
'''logging.Logger: Module level logger for all the logging needs of the module'''
_ATTR_BASIC = struct.Struct("<2IB")
'''struct.Struct: Struct to get basic information from the attribute header'''

#******************************************************************************
# MODULE LEVEL FUNCTIONS
#******************************************************************************
def get_attr_info(binary_view):
    '''Gets basic information from a binary stream to allow correct processing of
    the attribute header.

    This function allows the interpretation of the Attribute type, attribute length
    and if the attribute is non resident.

    Args:
        binary_view (memoryview of bytearray) - A binary stream with the
            information of the attribute

    Returns:
        An tuple with the attribute type, the attribute length, in bytes, and
        if the attribute is resident or not.
    '''
    global _ATTR_BASIC

    attr_type, attr_len, non_resident = _ATTR_BASIC.unpack(binary_view[:9])

    return (AttrTypes(attr_type), attr_len, bool(non_resident))

def _create_attrcontent_class(name, fields, inheritance=(object,), data_structure=None, extra_functions=None, docstring=""):
    '''Helper function that creates a class for attribute contents.

    This function creates is a boilerplate to create all the expected methods of
    an attributes. The basic methods work in the same way for all classes.

    Once it executes it defines a dynamic class with the methods "__init__",
    "__repr__" and "__eq__" based on the fields passed in the ``fields`` parameter.
    If the ``data_structure`` parameter is present, the classmethod ``get_representation_size``
    and the class variable ``_REPR`` will also be present.

    It is also possible to define the inheritance using this method by passing
    a list of classes in the ``inheritance`` parameter.

    If the ``extra_functions`` argument is present, they will be added to the
    class.

    Note:
        If the ``extra_functions`` has defined any of dinamically created methods,
        they will *replace* the ones created.


    Args:
        name (str): Name of the class that will be created.
        fields (tuple(str)): The attributes that will be added to the class.
        inherited (tuple(object)): List of objects that will be inherited by
            the new class
        extra_functions (dict(str : function)): A dictionary where the key
            will be the name of the function in the class and the content
            of the key is a function that will be bound to the class
        doctring (str): Class' docstring

    Returns:
        A new class with the ``name`` as it's name.
    '''

    def create_func_from_str(f_name, args, content, docstring=""):
        '''Helper function to create functions from strings.

        To improve performance, the standard functions are created at runtime
        based on the string derived from the content. This way the function, from
        the interpreter point of view, looks like statically defined.

        Note:
            This function should be used only for methods that will receive
            ``self`` (instace methods). The ``self`` argument is added automatically.

        Args:
            f_name (str): Function name
            args (list(str)): List of extra arguments that the function will receive
            content (str): Content of the function
            docstring (str): Function's docstring

        Returns:
            A new function object that can be inserted in the class.
        '''
        exec_namespace = {"__name__" : f"{f_name}"}
        new_args = ", ".join(["self"] + args)
        func_str = f"def {f_name}({new_args}): {content}"
        exec(func_str, exec_namespace)
        func = exec_namespace[f_name]
        func.__doc__ = docstring

        return func

    #creates the functions necessary for the new class
    slots = fields

    init_content = ", ".join([f"self.{field}" for field in fields]) + " = content"
    __init__ = create_func_from_str("__init__", [f"content=(None,)*{len(fields)}"],  init_content)

    temp = ", ".join([f"{field}={{self.{field}}}" for field in fields])
    repr = "return " + f"f\'{{self.__class__.__name__}}({temp})\'"
    __repr__ = create_func_from_str("__repr__", [],  repr)

    temp = " and ".join([f"self.{field} == other.{field}" for field in fields])
    eq = f"return {temp} if isinstance(other, {name}) else False"
    __eq__ = create_func_from_str("__eq__", ["other"], eq)

    @classmethod
    def get_representation_size(cls):
        return cls._REPR.size

    #adapted from namedtuple code
    # Modify function metadata to help with introspection and debugging
    for method in (__init__, get_representation_size.__func__, __eq__,
                   __repr__):
        method.__qualname__ = f'{name}.{method.__name__}'

    #map class namespace for the class creation
    namespace = {"__slots__" : slots,
                 "__init__" : __init__,
                 "__repr__" : __repr__,
                 "__eq__" : __eq__
                 }
    if data_structure is not None:
        namespace["_REPR"] = struct.Struct(data_structure)
        namespace["get_representation_size"] = get_representation_size
    if docstring:
        namespace["__doc__"] = docstring
    #some new mappings can be set or overload the ones defined
    if extra_functions is not None:
        for method in extra_functions.values():
            try:
                method.__qualname__ = f'{name}.{method.__name__}'
            except AttributeError:
                try:
                    method.__func__.__qualname__ = f'{name}.{method.__func__.__name__}'
                except AttributeError:
                    #if we got here, it is not a method or classmethod, must be an attribute
                    #TODO feels like a hack, change it
                    #TODO design a test for this
                    pass
        namespace = {**namespace, **extra_functions}

    #TODO check if docstring was provided, issue a warning

    new_class = type(name, inheritance, namespace)

    # adapted from namedtuple code
    # For pickling to work, the __module__ variable needs to be set to the frame
    # where the named tuple is created.  Bypass this step in environments where
    # sys._getframe is not defined (Jython for example) or sys._getframe is not
    # defined for arguments greater than 0 (IronPython), or where the user has
    # specified a particular module.
    try:
        new_class.__module__ = _sys._getframe(1).f_globals.get('__name__', '__main__')
    except (AttributeError, ValueError):
        pass

    return new_class

#******************************************************************************
# CLASSES
#******************************************************************************

#******************************************************************************
# DATA_RUN
#******************************************************************************
# Data runs are part of the non resident header.
#TODO replace the datarun tuple by a class?
# class DataRun():
#     def __init__(self, dr_len, offset):
#         self._dr_len = dr_len
#         self.offset = offset
#
#     def __getitem__(self, index):
#         if index == 0:
#             return self._dr_len
#         elif index == 1:
#             return self.offset
#         else:
#             raise IndexError("Invalid index for datarun object")
#
#     def __eq__(self, other):
#         if isinstance(other, self.__class__):
#             return self._dr_len == other._dr_len and self.offset == other.offset
#         else:
#             return False
#
#     def __len__(self):
#         return self._dr_len
#
#     def __repr__(self):
#         return f"{self.__class__.__name__}(dr_len={self._dr_len},offset={self.offset})"

class DataRuns():
    '''Represents the data runs of a non-resident attribute.

    When we have non resident attributes, it is necessary to map where in the
    disk the contents are. For that the NTFS uses data runs.

    Great resource for explanation and tests:
    https://flatcap.org/linux-ntfs/ntfs/concepts/data_runs.html

    Important:
        Calling ``len`` in this class returns the number of data runs, not the
        size in bytes.

    Args:
        data_runs (list of tuples) - A list of tuples representing the data run.
            The tuple has to have 2 elements, where the first element is the
            length of the data run and the second is the absolute offset

    Attributes:
        data_runs (list of tuples) - A list of tuples representing the data run.
            The tuple has to have 2 elements, where the first element is the
            length of the data run and the second is the absolute offset
    '''
    _INFO = struct.Struct("<B")

    def __init__(self, data_runs=[]):
        '''See class docstring.'''
        self.data_runs = data_runs #list of tuples

    @classmethod
    def create_from_binary(cls, binary_view):
        '''Creates a new object DataRuns from a binary stream. The binary
        stream can be represented by a byte string, bytearray or a memoryview of the
        bytearray.

        Args:
            binary_view (memoryview of bytearray) - A binary stream with the
                information of the attribute

        Returns:
            DataRuns: New object using hte binary stream as source
        '''
        nw_obj = cls()
        offset = 0
        previous_dr_offset = 0
        header_size = cls._INFO.size #"header" of a data run is always a byte

        while binary_view[offset] != 0:   #the runlist ends with an 0 as the "header"
            header = cls._INFO.unpack(binary_view[offset:offset+header_size])[0]
            length_len = header & 0x0F
            length_offset = (header & 0xF0) >> 4

            temp_len = offset+header_size+length_len #helper variable just to make things simpler
            dr_length = int.from_bytes(binary_view[offset+header_size:temp_len], "little", signed=False)
            if length_offset: #the offset is relative to the previous data run
                dr_offset = int.from_bytes(binary_view[temp_len:temp_len+length_offset], "little", signed=True) + previous_dr_offset
                previous_dr_offset = dr_offset
            else: #if it is sparse, requires a a different approach
                dr_offset = None
            offset += header_size + length_len + length_offset
            nw_obj.data_runs.append((dr_length, dr_offset))
            #nw_obj.data_runs.append(DataRun(dr_length, dr_offset))

        _MOD_LOGGER.debug("DataRuns object created successfully")

        return nw_obj

    def __len__(self):
        '''Returns the number of data runs'''
        return len(self.data_runs)

    def __iter__(self):
        '''Return the iterator for the representation of the list.'''
        return iter(self.data_runs)

    def __getitem__(self, index):
        '''Return a specific data run'''
        return _getitem(self.data_runs, index)

    def __repr__(self):
        'Return a nicely formatted representation string'
        return f'{self.__class__.__name__}(data_runs={self.data_runs})'

class BaseAttributeHeader():
    '''Represents the common contents of the Attribute Header.

    Independently if the attribute is resident on non-resident, all of them
    have a common set a data. This class represents this common set of attributes
    and is not meant to be used directly, but to be inherited by the resident
    header and non resident header classes.

    Note:
        This class receives an Iterable as argument, the "Parameters/Args" section
        represents what must be inside the Iterable. The Iterable MUST preserve
        order or things might go boom.

    Args:
        content[0] (:obj:`AttrTypes`): Type of the attribute
        content[1] (int): Attribute's length, in bytes
        content[2] (bool): True if non resident attribute, False otherwise
        content[3] (:obj:`AttrFlags`): Attribute flags
        content[4] (int): Attribute ID
        content[5] (str): Attribute name

    Attributes:
        attr_type_id (:obj:`AttrTypes`): Type of the attribute
        attr_len (int): Attribute's length, in bytes
        non_resident (bool): True if non resident attribute, False otherwise
        flags (:obj:`AttrFlags`): Attribute flags
        attr_id (int): Attribute ID
        attr_name (str): Attribute name
    '''
    _REPR_STRING = "2I2B3H"

    _REPR = struct.Struct("<2I2B3H")
    ''' Attribute type id - 4 (AttrTypes)
        Length of the attribute - 4 (in bytes)
        Non-resident flag - 1 (0 - resident, 1 - non-resident)
        Length of the name - 1 (in number of characters)
        Offset to name - 2
        Flags - 2 (AttrFlags)
        Attribute id - 2
    '''

    __slots__ = ("attr_type_id", "attr_len", "non_resident", "flags", "attr_id",
        "attr_name")

    def __init__(self, content=(None,)*6):
        '''See class docstring.'''
        self.attr_type_id, self.attr_len, self.non_resident, self.flags, self.attr_id, \
        self.attr_name = content


    @classmethod
    def create_from_binary(cls, binary_view):
        '''Creates a new object BaseAttributeHeader from a binary stream. The binary
        stream can be represented by a byte string, bytearray or a memoryview of the
        bytearray.

        Args:
            binary_view (memoryview of bytearray) - A binary stream with the
                information of the attribute

        Returns:
            BaseAttributeHeader: New object using hte binary stream as source
        '''
        attr_type, attr_len, non_resident, name_len, name_offset, flags, attr_id = cls._REPR.unpack(binary_view[:cls._REPR.size])

        if name_len:
            name = binary_view[name_offset:name_offset+(2*name_len)].tobytes().decode("utf_16_le")
        else:
            name = None

        nw_obj = cls((AttrTypes(attr_type), attr_len, bool(non_resident), AttrFlags(flags), attr_id, name ))

        return nw_obj

    @classmethod
    def get_representation_size(cls):
        '''Return the header size WITHOUT accounting for a possible named attribute.'''
        return cls._REPR.size

    def __len__(self):
        '''Returns the logical size of the attribute'''
        return self.attr_len

    def __repr__(self):
        'Return a nicely formatted representation string'
        return (f'{self.__class__.__name__}(attr_type_id={str(self.attr_type_id)},'
                f'attr_len={self.attr_len}, nonresident_flag={self.non_resident},'
                f'flags={str(self.flags)}, attr_id={self.attr_id},'
                f'resident_header={self.resident_header}, non_resident_header={self.non_resident_header}, attr_name={self.attr_name})'
               )

class ResidentAttrHeader(BaseAttributeHeader):
    '''Represents the the attribute header when the attribute is resident.

    Note:
        This class receives an Iterable as argument, the "Parameters/Args" section
        represents what must be inside the Iterable. The Iterable MUST preserve
        order or things might go boom.

    Args:
        content_basic (Iterable): See BaseAttributeHeader documentation
        content_specific[0] (int): Content's length, in bytes
        content_specific[1] (int): Content offset
        content_specific[2] (int): Indexed flag

    Attributes:
        content_len (int): Content's length, in bytes
        content_offset (int): Content offset
        indexed_flag (int): Indexed flag
    '''

    _REPR = struct.Struct("".join(["<", BaseAttributeHeader._REPR_STRING, "IHBx"]))
    '''
    BASIC HEADER
        Attribute type id - 4 (AttrTypes)
        Length of the attribute - 4 (in bytes)
        Non-resident flag - 1 (0 - resident, 1 - non-resident)
        Length of the name - 1 (in number of characters)
        Offset to name - 2
        Flags - 2 (AttrFlags)
        Attribute id - 2
    RESIDENT HEADER COMPLEMENT
        Content length - 4
        Content offset - 2
        Indexed flag - 1
        Padding - 1
    '''

    __slots__ = ("content_len", "content_offset", "indexed_flag")

    def __init__(self, content_basic=(None,)*6, content_specific=(None,)*3):
        super().__init__(content_basic)
        self.content_len, self.content_offset, self.indexed_flag = content_specific
        pass

    @classmethod
    def get_representation_size(cls):
        '''Return the header size WITHOUT accounting for a possible named attribute.'''
        return cls._REPR.size

    @classmethod
    def create_from_binary(cls, binary_view):
        '''Creates a new object AttributeHeader from a binary stream. The binary
        stream can be represented by a byte string, bytearray or a memoryview of the
        bytearray.

        Args:
            binary_view (memoryview of bytearray) - A binary stream with the
                information of the attribute

        Returns:
            AttributeHeader: New object using hte binary stream as source
        '''
        attr_type, attr_len, non_resident, name_len, name_offset, flags, attr_id, \
        content_len, content_offset, indexed_flag = cls._REPR.unpack(binary_view[:cls._REPR.size])

        if name_len:
            name = binary_view[name_offset:name_offset+(2*name_len)].tobytes().decode("utf_16_le")
        else:
            name = None

        nw_obj = cls((AttrTypes(attr_type), attr_len, bool(non_resident), AttrFlags(flags), attr_id, name),
                        (content_len, content_offset, indexed_flag))

        return nw_obj


    def __repr__(self):
        'Return a nicely formatted representation string'
        return (f'{self.__class__.__name__}(attr_type_id={str(self.attr_type_id)},'
                f'attr_len={self.attr_len}, nonresident_flag={self.non_resident},'
                f'flags={str(self.flags)}, attr_id={self.attr_id}, attr_name={self.attr_name}'
                f'content_len={self.content_len}, content_offset={self.content_offset}),indexed_flag={self.indexed_flag}'
                )

class NonResidentAttrHeader(BaseAttributeHeader):
    '''Represents the non-resident header of an attribute.'''

    _REPR = struct.Struct("".join(["<", BaseAttributeHeader._REPR_STRING, "2Q2H4x3Q"]))
    '''
    BASIC HEADER
        Attribute type id - 4 (AttrTypes)
        Length of the attribute - 4 (in bytes)
        Non-resident flag - 1 (0 - resident, 1 - non-resident)
        Length of the name - 1 (in number of characters)
        Offset to name - 2
        Flags - 2 (AttrFlags)
        Attribute id - 2
    NON-RESIDENT HEADER COMPLEMENT
        Start virtual cluster number - 8
        End virtual cluster number - 8
        Runlist offset - 2
        Compression unit size - 2
        Padding - 4
        Allocated size of the stream - 8
        Current size of the stream - 8
        Initialized size of the stream - 8
        Data runs - dynamic
    '''

    __slots__ = ("start_vcn", "end_vcn", "rl_offset", "compress_usize", "alloc_sstream", "curr_sstream", "init_sstream", "data_runs")

    def __init__(self, content_basic=(None,)*6, content_specific=(None,)*7, data_runs=None):
        '''Creates a NonResidentAttrHeader object. The content has to be an iterable
        with precisely 9 elements in order.
        If content is not provided, a 9 element tuple, where all elements are
        None, is the default argument

        Args:
            content (iterable), where:
                [0] (int) - start vcn
                [1] (int) - end vcn
                [2] (int) - datarun list offset
                [3] (int) - compression unit size
                [4] (int) - allocated data size
                [5] (int) - current data size
                [6] (int) - initialized data size
            data_runs (list of DataRuns) - A list with all dataruns relative
                to this particular header. If nothing is provided, the default
                argument is 'None'.
        '''
        super().__init__(content_basic)
        self.start_vcn, self.end_vcn, self.rl_offset, self.compress_usize, \
        self.alloc_sstream, self.curr_sstream, self.init_sstream = content_specific
        self.data_runs = data_runs

    @classmethod
    def get_representation_size(cls):
        '''Return the header size, does not account for the number of data runs'''
        return cls._REPR.size

    @classmethod
    def create_from_binary(cls, load_dataruns, binary_view):
        '''Creates a new object NonResidentAttrHeader from a binary stream. The binary
        stream can be represented by a byte string, bytearray or a memoryview of the
        bytearray.

        Args:
            load_dataruns (bool) - Indicates if the dataruns are to be loaded
            binary_view (memoryview of bytearray) - A binary stream with the
                information of the attribute
            non_resident_offset (int) - The offset where the non resident header
                begins

        Returns:
            NonResidentAttrHeader: New object using hte binary stream as source
        '''
        attr_type, attr_len, non_resident, name_len, name_offset, flags, attr_id, \
            start_vcn, end_vcn, rl_offset, compress_usize, alloc_sstream, curr_sstream, \
            init_sstream = cls._REPR.unpack(binary_view[:cls._REPR.size])

        if name_len:
            name = binary_view[name_offset:name_offset+(2*name_len)].tobytes().decode("utf_16_le")
        else:
            name = None

        #content = cls._REPR.unpack(binary_view[non_resident_offset:non_resident_offset+cls._REPR.size])
        nw_obj = cls((AttrTypes(attr_type), attr_len, bool(non_resident), AttrFlags(flags), attr_id, name),
            (start_vcn, end_vcn, rl_offset, compress_usize, alloc_sstream, curr_sstream, init_sstream))

        if load_dataruns:
            nw_obj.data_runs = DataRuns.create_from_binary(binary_view[nw_obj.rl_offset:])
        _MOD_LOGGER.debug("NonResidentAttrHeader object created successfully")

        return nw_obj

    def __repr__(self):
        'Return a nicely formatted representation string'
        return (f'{self.__class__.__name__}(attr_type_id={str(self.attr_type_id)},'
                f'attr_len={self.attr_len}, nonresident_flag={self.non_resident},'
                f'flags={str(self.flags)}, attr_id={self.attr_id}, attr_name={self.attr_name},'
                f'start_vcn={self.start_vcn}, end_vcn={self.end_vcn}, rl_offset={self.rl_offset},'
                f'compress_usize={self.compress_usize}, alloc_sstream={self.alloc_sstream},'
                f'curr_sstream={self.curr_sstream}, init_sstream={self.init_sstream}, data_runs={self.data_runs})'
                )

#------------------------------------------------------------------------------
#******************************************************************************
#******************************************************************************
# ATTRIBUTE CONTENT CLASSES
#******************************************************************************
#******************************************************************************
#------------------------------------------------------------------------------

#******************************************************************************
# ABSTRACT CLASS FOR ATTRIBUTE CONTENT
#******************************************************************************
class AttributeContentBase(metaclass=ABCMeta):
    '''Base class for attribute's content.

    This class is an interface to all the attribute's contents. It can't be
    instantiated and serves only a general interface.
    '''

    @classmethod
    @abstractmethod
    def create_from_binary(cls, binary_stream):
        '''Creates an object from from a binary stream.

        Args:
            binary_stream (memoryview): A buffer access to the underlying binary
                stream

        Returns:
            A new object of whatever type has overloaded the method.
        '''
        pass

    @abstractmethod
    def __len__(self):
        '''Get the actual size of the content, in bytes, as some attributes have variable sizes.'''
        pass

    @abstractmethod
    def __eq__(self, other):
        pass

class AttributeContentNoRepr(AttributeContentBase):
    '''Base class for attribute's content that don't have a fixed representation.

    This class is an interface to the attribute's contents. It can't be
    instantiated and serves only a general interface.
    '''
    pass

class AttributeContentRepr(AttributeContentBase):
    '''Base class for attribute's content that don't have a fixed representation.

    This class is an interface to the attribute's contents. It can't be
    instantiated and serves only a general interface.
    '''

    @classmethod
    @abstractmethod
    def get_representation_size(cls):
        '''Get the representation size, in bytes, based on defined struct

        Returns:
            An ``int`` with the size of the structure
        '''
        pass


#******************************************************************************
# TIMESTAMPS class
#******************************************************************************
def _len_ts(self):
    return Timestamps._REPR.size

def _from_binary_ts(cls, binary_stream):
    """See base class."""
    repr = cls._REPR

    if len(binary_stream) != repr.size:
        raise ContentError("Invalid binary stream size")

    content = repr.unpack(binary_stream)
    nw_obj = cls()
    nw_obj.created, nw_obj.changed, nw_obj.mft_changed, nw_obj.accessed = \
        convert_filetime(content[0]), convert_filetime(content[1]), \
        convert_filetime(content[2]), convert_filetime(content[3])

    _MOD_LOGGER.debug("Attempted to unpack Timestamp from \"%s\"\nResult: %s", binary_stream.tobytes(), nw_obj)

    return nw_obj

def _astimezone_ts(self, timezone):
    """Changes the time zones of all timestamps.

    Receives a new timezone and applies to all timestamps, if necessary.

    Args:
        timezone (:obj:`tzinfo`): Time zone to be applied

    Returns:
        A new ``Timestamps`` object if the time zone changes, otherwise returns ``self``.
    """
    if self.created.tzinfo is timezone:
        return self
    else:
        nw_obj = Timestamps((None,)*4)
        nw_obj.created = self.created.astimezone(timezone)
        nw_obj.changed = self.changed.astimezone(timezone)
        nw_obj.mft_changed = self.mft_changed.astimezone(timezone)
        nw_obj.accessed = self.accessed.astimezone(timezone)

        return nw_obj

_docstring_ts = '''Represents a group of timestamps based on how MFT records.

Aggregates the entries for timesamps when dealing with standard NTFS timestamps,
e.g., created, changed, mft change and accessed. All attributes are time zone
aware.

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (:obj:`datetime`): Created timestamp
    content[1] (datetime): Changed timestamp
    content[2] (datetime): MFT change timestamp
    content[3] (datetime): Accessed timestamp

Attributes:
    created (datetime): A datetime with the created timestamp
    changed (datetime): A datetime with the changed timestamp
    mft_changed (datetime): A datetime with the mft_changed timestamp
    accessed (datetime): A datetime with the accessed timestamp
'''

_ts_namespace = {"__len__" : _len_ts,
                 "create_from_binary" : classmethod(_from_binary_ts),
                 "astimezone" : _astimezone_ts
                 }

Timestamps = _create_attrcontent_class("Timestamps", ("created", "changed", "mft_changed", "accessed"),
        inheritance=(AttributeContentRepr,), data_structure="<4Q",
        extra_functions=_ts_namespace, docstring=_docstring_ts)

#******************************************************************************
# STANDARD_INFORMATION ATTRIBUTE
#******************************************************************************
def _len_stdinfo(self):
    return StandardInformation._TIMESTAMP_SIZE + StandardInformation._REPR.size

def _from_binary_stdinfo(cls, binary_stream):
    """See base class."""
    '''
        TIMESTAMPS(32)
            Creation time - 8
            File altered time - 8
            MFT/Metadata altered time - 8
            Accessed time - 8
        Flags - 4 (FileInfoFlags)
        Maximum number of versions - 4
        Version number - 4
        Class id - 4
        Owner id - 4 (NTFS 3+)
        Security id - 4 (NTFS 3+)
        Quota charged - 8 (NTFS 3+)
        Update Sequence Number (USN) - 8 (NTFS 3+)
    '''

    if len(binary_stream) == cls._REPR.size: #check if it is v3 by size of the stram
        t_created, t_changed, t_mft_changed, t_accessed, flags, m_ver, ver, \
            c_id, o_id, s_id, quota_charged, usn = cls._REPR.unpack(binary_stream)
        nw_obj = cls(
            (   Timestamps((convert_filetime(t_created), convert_filetime(t_changed),
                            convert_filetime(t_mft_changed), convert_filetime(t_accessed))
            ), FileInfoFlags(flags), m_ver, ver, c_id, o_id, s_id, quota_charged, usn))
    else:
        #if the content is not using v3 extension, added the missing stuff for consistency
        t_created, t_changed, t_mft_changed, t_accessed, flags, m_ver, ver, \
            c_id  = cls._REPR_NO_NFTS_3_EXTENSION.unpack(binary_stream)
        nw_obj = cls(
            (   Timestamps((convert_filetime(t_created), convert_filetime(t_changed),
                            convert_filetime(t_mft_changed), convert_filetime(t_accessed))
            ), FileInfoFlags(flags), m_ver, ver, c_id, None, None, None, None))

    _MOD_LOGGER.debug("Attempted to unpack STANDARD_INFORMATION from \"%s\"\nResult: %s", binary_stream.tobytes(), nw_obj)

    return nw_obj

_docstring_stdinfo = '''Represents the STANDARD_INFORMATION content.

Has all the data structures to represent a STANDARD_INFORMATION attribute,
allowing everything to be accessed with python objects/types.

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (:obj:`Timestamps`): Timestamp object
    content[1] (:obj:`FileInfoFlags`): A FIleInfoFlags object with the flags
        for this object
    content[2] (int): Maximum number of allowed versions
    content[3] (int): Current version number
    content[4] (int): Class id
    content[5] (int): Owner id
    content[6] (int): Security id
    content[7] (int): Quota charged
    content[8] (int): Update Sequence Number (USN)

Attributes:
    timestamps (:obj:`Timestamps`): All attribute's timestamps
    flags (:obj:`FileInfoFlags`): STANDARD_INFORMATION flags for the file
    max_n_versions (int): Maximum number of allowed versions
    version_number (int): Current version number
    class_id (int): Class id
    owner_id (int): Owner id
    security_id (int): Security id
    quota_charged (int): Quota charged
    usn (int): Update Sequence Number (USN)
'''

_stdinfo_namespace = {"__len__" : _len_stdinfo,
                 "create_from_binary" : classmethod(_from_binary_stdinfo),
                 "_REPR_NO_NFTS_3_EXTENSION" : struct.Struct("<4Q4I")
                 }

StandardInformation = _create_attrcontent_class("StandardInformation",
            ("timestamps", "flags", "max_n_versions", "version_number", "class_id",
                "owner_id", "security_id", "quota_charged", "usn"),
        inheritance=(AttributeContentRepr,), data_structure="<4Q4I2I2Q",
        extra_functions=_stdinfo_namespace, docstring=_docstring_stdinfo)

#******************************************************************************
# ATTRIBUTE_LIST ATTRIBUTE
#******************************************************************************
def _from_binary_attrlist_e(cls, binary_stream):
    """See base class."""
    '''
        Attribute type - 4
        Length of a particular entry - 2
        Length of the name - 1 (in characters)
        Offset to name - 1
        Starting VCN - 8
        File reference - 8
        Attribute ID - 1
        Name (unicode) - variable
    '''

    attr_type, entry_len, name_len, name_off, s_vcn, f_tag, attr_id = cls._REPR.unpack(binary_stream[:cls._REPR.size])
    if name_len:
        name = binary_stream[name_off:name_off+(2*name_len)].tobytes().decode("utf_16_le")
    else:
        name = None
    file_ref, file_seq = get_file_reference(f_tag)
    nw_obj = cls((AttrTypes(attr_type), entry_len, name_off, s_vcn, file_ref, file_seq, attr_id, name))

    _MOD_LOGGER.debug("Attempted to unpack ATTRIBUTE_LIST Entry from \"%s\"\nResult: %s", binary_stream.tobytes(), nw_obj)

    return nw_obj

def _len_attrlist_e(self):
    '''Returns the size of the entry, in bytes'''
    return self._entry_len

_docstring_attrlist_e = '''Represents an entry for ATTRIBUTE_LIST.

Has all the data structures to represent one entry of the ATTRIBUTE_LIST
content allowing everything to be accessed with python objects/types.

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (:obj:`AttrTypes`): Type of the attribute in the entry
    content[1] (int): Length of the entry, in bytes
    content[2] (int): Length of the name, in bytes
    content[3] (int): Offset to the name, in bytes
    content[4] (int): Start VCN
    content[5] (int): File reference number
    content[6] (int): File sequence number
    content[7] (int): Attribute ID
    content[8] (int): Name

Attributes:
    attr_type (:obj:`Timestamps`): Type of the attribute in the entry
    name_offset (int): Offset to the name, in bytes
    start_vcn (int): Start VCN
    file_ref (int): File reference number
    file_seq (int): File sequence number
    attr_id (int): Attribute ID
    name (int): Name
'''

_attrlist_e_namespace = {"__len__" : _len_attrlist_e,
                 "create_from_binary" : classmethod(_from_binary_attrlist_e)
                 }

AttributeListEntry = _create_attrcontent_class("AttributeListEntry",
            ("attr_type", "_entry_len", "name_offset", "start_vcn",
                "file_ref", "file_seq", "attr_id", "name"),
        inheritance=(AttributeContentRepr,), data_structure="<IH2B2QH",
        extra_functions=_attrlist_e_namespace, docstring=_docstring_attrlist_e)

#-----------------------------------------------------------------------------

def _from_binary_attrlist(cls, binary_stream):
    """See base class."""
    _attr_list = []
    offset = 0

    while True:
        entry = AttributeListEntry.create_from_binary(binary_stream[offset:])
        offset += len(entry)
        _attr_list.append(entry)
        if offset >= len(binary_stream):
            break
        _MOD_LOGGER.debug("Next AttributeListEntry offset = %d", offset)
    _MOD_LOGGER.debug("Attempted to unpack ATTRIBUTE_LIST Entry from \"%s\"\nResult: %s", binary_stream.tobytes(), _attr_list)

    return cls(_attr_list)

def _len_attrlist(self):
    '''Return the number of entries in the attribute list'''
    return len(self._attr_list)

def _iter_attrlist(self):
    return iter(self._attr_list)

def _gitem_attrlist(self, index):
    return _getitem(self._attr_list, index)

_docstring_attrlist = '''Represents the contents for the ATTRIBUTE_LIST attribute.

Is a list of AttributeListEntry. It behaves as list in python, you can iterate
over it, access by member, etc.

Important:
    Using the ``len()`` method on the objects of this class returns the number
    of elements in the list.

Args:
    content (list(:obj:`AttributeListEntry`)): List of AttributeListEntry
'''

_attrlist_namespace = {"__len__" : _len_attrlist,
                       "__iter__" : _iter_attrlist,
                       "__getitem__" : _gitem_attrlist,
                       "create_from_binary" : classmethod(_from_binary_attrlist)
                 }

AttributeList = _create_attrcontent_class("AttributeList",
            ("_attr_list",),
        inheritance=(AttributeContentNoRepr,), data_structure=None,
        extra_functions=_attrlist_namespace, docstring=_docstring_attrlist)

#******************************************************************************
# OBJECT_ID ATTRIBUTE
#******************************************************************************
def _from_binary_objid(cls, binary_stream):
    """See base class."""
    uid_size = ObjectID._UUID_SIZE

    #some entries might not have all four ids, this line forces
    #to always create 4 elements, so contruction is easier
    uids = [UUID(bytes_le=binary_stream[i*uid_size:(i+1)*uid_size].tobytes()) if i * uid_size < len(binary_stream) else None for i in range(0,4)]
    _MOD_LOGGER.debug("Attempted to unpack OBJECT_ID Entry from \"%s\"\nResult: %s", binary_stream.tobytes(), uids)

    return cls(uids)

def _len_objid(self):
    '''Get the actual size of the content, as some attributes have variable sizes'''
    try:
        return self._size
    except AttributeError:
        temp = (self.object_id, self.birth_vol_id, self.birth_object_id, self.birth_domain_id)
        self._size = sum([ObjectID._UUID_SIZE for data in temp if data is not None])
        return self._size

_docstring_objid = '''Represents the content of the OBJECT_ID attribute.

Important:
    When reading from binary, some entries may not have all the members,
    in this case the code creates None entries.

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (:obj:`UUID`): Object id
    content[1] (:obj:`UUID`): Birth volume id
    content[2] (:obj:`UUID`): Birth object id
    content[3] (:obj:`UUID`): Birth domain id

Attributes:
    object_id (UUID): Unique ID assigned to file
    birth_vol_id (UUID): ID of the volume where the file was created
    birth_object_id (UUID): Original Object ID of the file
    birth_domain_id (UUID): Domain where the object was created
'''

_objid_namespace = {"__len__" : _len_objid,
                       "_UUID_SIZE" : 16,
                       "create_from_binary" : classmethod(_from_binary_objid)
                 }

ObjectID = _create_attrcontent_class("ObjectID",
            ("object_id", "birth_vol_id", "birth_object_id", "birth_domain_id"),
        inheritance=(AttributeContentNoRepr,), data_structure=None,
        extra_functions=_objid_namespace, docstring=_docstring_objid)


#******************************************************************************
# VOLUME_NAME ATTRIBUTE
#******************************************************************************
def _from_binary_volname(cls, binary_stream):
    """See base class."""
    name = binary_stream.tobytes().decode("utf_16_le")

    _MOD_LOGGER.debug("Attempted to unpack VOLUME_NAME Entry from \"%s\"\nResult: %s", binary_stream.tobytes(), name)

    return cls(name)

def _len_volname(self):
    """Returns the size of the attribute, in bytes, encoded in utf_16_le"""
    return len(self.name.encode("utf_16_le"))

_docstring_volname = """Represents the content of the VOLUME_NAME attribute.

Args:
    name (str): Volume's name

Attributes:
    name (str): Volume's name
"""

_volname_namespace = {"__len__" : _len_volname,
                       "create_from_binary" : classmethod(_from_binary_volname)
                 }

VolumeName = _create_attrcontent_class("VolumeName",
            ("name", ),
        inheritance=(AttributeContentNoRepr,), data_structure=None,
        extra_functions=_volname_namespace, docstring=_docstring_volname)

#******************************************************************************
# VOLUME_INFORMATION ATTRIBUTE
#******************************************************************************
def _from_binary_volinfo(cls, binary_stream):
    """See base class."""
    content = cls._REPR.unpack(binary_stream)

    nw_obj = cls(content)
    nw_obj.vol_flags = VolumeFlags(content[2])

    _MOD_LOGGER.debug("Attempted to unpack VOLUME_INFORMATION Entry from \"%s\"\nResult: %s", binary_stream.tobytes(), content)

    return nw_obj

def _len_volinfo(self):
    '''Returns the length of the attribute'''
    return VolumeInformation._REPR.size

_docstring_volinfo = '''Represents the content of the VOLUME_INFORMATION attribute

Interprets the volume information as per viewed by MFT. Contains information
like version and the state of the volume.

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (int): Major version
    content[1] (int): Minor version
    content[2] (:obj:`VolumeFlags`): Volume flags

Attributes:
    major_ver (int): Major version
    minor_ver (int): Minor version
    vol_flags (:obj:`VolumeFlags`): Volume flags
'''

_volinfo_namespace = {"__len__" : _len_volinfo,
                       "create_from_binary" : classmethod(_from_binary_volinfo)
                 }

VolumeInformation = _create_attrcontent_class("VolumeInformation",
            ("major_ver", "minor_ver", "vol_flags"),
        inheritance=(AttributeContentRepr,), data_structure="<8x2BH",
        extra_functions=_volinfo_namespace, docstring=_docstring_volinfo)

#******************************************************************************
# FILENAME ATTRIBUTE
#******************************************************************************
def _from_binary_filename(cls, binary_stream):
    """See base class."""
    ''' File reference to parent directory - 8
        TIMESTAMPS(32)
            Creation time - 8
            File altered time - 8
            MFT/Metadata altered time - 8
            Accessed time - 8
        Allocated size of file - 8 (multiple of the cluster size)
        Real size of file - 8 (actual file size, might also be stored by the directory)
        Flags - 4
        Reparse value - 4
        Name length - 1 (in characters)
        Name type - 1
        Name - variable
    '''

    f_tag, t_created, t_changed, t_mft_changed, t_accessed, alloc_fsize, \
        real_fsize, flags, reparse_value, name_len, name_type = cls._REPR.unpack(binary_stream[:cls._REPR.size])
    name = binary_stream[cls._REPR.size:].tobytes().decode("utf_16_le")
    file_ref, file_seq = get_file_reference(f_tag)

    nw_obj = cls((file_ref, file_seq,
           Timestamps((convert_filetime(t_created), convert_filetime(t_changed),
                        convert_filetime(t_mft_changed), convert_filetime(t_accessed))
        ), alloc_fsize, real_fsize, FileInfoFlags(flags), reparse_value, NameType(name_type), name))

    _MOD_LOGGER.debug("Attempted to unpack FILENAME from \"%s\"\nResult: %s", binary_stream.tobytes(), nw_obj)

    return nw_obj

def _len_filename(self):
    return  FileName._REPR.size + len(name.encode("utf_16_le"))

_docstring_filename = '''Represents the content of a FILENAME attribute.

The FILENAME attribute is one of the most important for MFT. It is not a mandatory
field, but if present, holds multiple timestamps, flags of the file and the name
of the file. It may be present multiple times.

Warning:
    The information related to "allocated file size" and "real file size"
    in this attribute is NOT reliable. Blame Microsoft. If you want a more
    reliable information, use the ``Datastream`` objects in the api module.

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (int): Parent reference
    content[1] (int): Parent sequence
    content[2] (:obj:`Timestamps`): Filename timestamps
    content[3] (int): Allocated size of the file
    content[4] (int): Logica/Real file size
    content[5] (:obj:`FileInfoFlags`): File flags
    content[6] (int): Reparse value
    content[7] (int): Name length
    content[8] (:obj:`NameType`): Name type
    content[9] (str): Name

Attributes:
    parent_ref (int): Parent refence
    parent_seq (int): Parent sequence
    timestamps (:obj:`Timestamps`): Filename timestamps
    alloc_file_size (int): Allocated size of the file
    real_file_size (int): Logica/Real file size
    flags (:obj:`FileInfoFlags`): File flags
    reparse_value (int): Reparse value
    name_type (:obj:`NameType`): Name type
    name (str): Name
'''

_filename_namespace = {"__len__" : _len_filename,
                       "create_from_binary" : classmethod(_from_binary_filename)
                 }

FileName = _create_attrcontent_class("FileName",
            ("parent_ref", "parent_seq", "timestamps", "alloc_file_size",
            "real_file_size", "flags", "reparse_value", "name_type", "name"),
        inheritance=(AttributeContentRepr,), data_structure="<7Q2I2B",
        extra_functions=_filename_namespace, docstring=_docstring_filename)

#******************************************************************************
# DATA ATTRIBUTE
#******************************************************************************
def _from_binary_data(cls, binary_stream):
    """See base class."""
    return cls(binary_stream.tobytes())

def _len_data(self):
    return len(self.content)

_docstring_data = """Represents the content of a DATA attribute.

This is a placeholder class to the data attribute. By itself, it does
very little and holds almost no information. If the data is resident, holds the
content and the size.

Args:
    binary_data (:obj:`bytes`): Data content

Attributes:
    content (:obj:`bytes`): Data content
"""

_data_namespace = {"__len__" : _len_data,
                       "create_from_binary" : classmethod(_from_binary_data)
                 }

Data = _create_attrcontent_class("Data",
            ("content", ),
        inheritance=(AttributeContentNoRepr,), data_structure=None,
        extra_functions=_data_namespace, docstring=_docstring_data)

#******************************************************************************
# INDEX_ROOT ATTRIBUTE
#******************************************************************************
def _from_binary_idx_nh(cls, binary_stream):
    """See base class."""
    ''' Offset to start of index entry - 4
        Offset to end of used portion of index entry - 4
        Offset to end of the allocated index entry - 4
        Flags - 4
    '''
    nw_obj = cls(cls._REPR.unpack(binary_stream[:cls._REPR.size]))

    _MOD_LOGGER.debug("Attempted to unpack Index Node Header Entry from \"%s\"\nResult: %s", binary_stream.tobytes(), nw_obj)

    return nw_obj

def _len_idx_nh(self):
    return IndexNodeHeader._REPR.size

_docstring_idx_nh = '''Represents the Index Node Header, that is always present in the INDEX_ROOT
and INDEX_ALLOCATION attribute.

The composition of an INDEX_ROOT and INDEX_ALLOCATION always start with
a header. This class represents this header.

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (int): Start offset
    content[1] (int): End offset
    content[2] (int): Allocated size of the node
    content[3] (int): Non-leaf node Flag (has subnodes)

Attributes:
    start_offset (int): Start offset
    end_offset (int): End offset
    end_alloc_offset (int): Allocated size of the node
    flags (int): Non-leaf node Flag (has subnodes)
'''

_idx_nh_namespace = {"__len__" : _len_idx_nh,
                       "create_from_binary" : classmethod(_from_binary_idx_nh)
                 }

IndexNodeHeader = _create_attrcontent_class("IndexNodeHeader",
            ("start_offset", "end_offset", "end_alloc_offset", "flags"),
        inheritance=(AttributeContentRepr,), data_structure="<4I",
        extra_functions=_idx_nh_namespace, docstring=_docstring_idx_nh)

#------------------------------------------------------------------------------

def _from_binary_idx_e(cls, binary_stream, content_type=None):
    """See base class."""
    #TODO don't save this here and overload later?
    #TODO confirm if this is really generic or is always a file reference
    ''' Undefined - 8
        Length of entry - 2
        Length of content - 2
        Flags - 4
        Content - variable
        VCN of child node - 8 (exists only if flag is set, aligned to a 8 byte boundary)
    '''
    repr_size = cls._REPR.size
    generic, entry_len, cont_len, flags = cls._REPR.unpack(binary_stream[:repr_size])
    vcn_child_node = (None,)

    #if content is known (filename), create a new object to represent the content
    if content_type is AttrTypes.FILE_NAME and cont_len:
        binary_content = FileName.create_from_binary(binary_stream[repr_size:repr_size+cont_len])
    else:
        binary_content = binary_stream[repr_size:repr_size+cont_len].tobytes()
    #if there is a next entry, we need to pad it to a 8 byte boundary
    if flags & IndexEntryFlags.CHILD_NODE_EXISTS:
        temp_size = repr_size + cont_len
        boundary_fix = (entry_len - temp_size) % 8
        vcn_child_node = cls._REPR_VCN.unpack(binary_stream[temp_size+boundary_fix:temp_size+boundary_fix+8])

    nw_obj = cls((generic, entry_len, cont_len, IndexEntryFlags(flags), binary_content, vcn_child_node))

    _MOD_LOGGER.debug("Attempted to unpack Index Entry from \"%s\"\nResult: %s", binary_stream.tobytes(), nw_obj)

    return nw_obj

def _len_idx_e(self):
    return self._entry_len

_docstring_idx_e = '''Represents an entry in the index.

An Index, from the MFT perspective is composed of multiple entries. This class
represents these entries. Normally entries contain a FILENAME attribute.
Note the entry can have other types of content, for these cases the class
saves the raw bytes

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (int): File reference?
    content[1] (int): Length of the entry
    content[2] (int): Length of the content
    content[3] (:obj:`IndexEntryFlags`): Flags
    content[4] (:obj:`FileName` or bytes): Content of the entry
    content[5] (int): VCN child node

Attributes:
    generic (int): File reference?
    content_len (int): Length of the content
    flags (:obj:`IndexEntryFlags`): Flags
    content (:obj:`FileName` or bytes): Content of the entry
    vcn_child_node (int): VCN child node
'''

_idx_e_namespace = {"__len__" : _len_idx_e,
                    "_REPR_VCN" : struct.Struct("<Q"),
                    "create_from_binary" : classmethod(_from_binary_idx_e)
                 }

IndexEntry = _create_attrcontent_class("IndexEntry",
            ("generic", "_entry_len", "content_len", "flags", "content", "vcn_child_node"),
        inheritance=(AttributeContentRepr,), data_structure="<Q2HI",
        extra_functions=_idx_e_namespace, docstring=_docstring_idx_e)

#------------------------------------------------------------------------------


def _from_binary_idx_root(cls, binary_stream):
    """See base class."""
    ''' Attribute type - 4
        Collation rule - 4
        Bytes per index record - 4
        Clusters per index record - 1
        Padding - 3
    '''
    attr_type, collation_rule, b_per_idx_r, c_per_idx_r = cls._REPR.unpack(binary_stream[:cls._REPR.size])
    node_header = IndexNodeHeader.create_from_binary(binary_stream[cls._REPR.size:])
    attr_type = AttrTypes(attr_type) if attr_type else None
    index_entry_list = []

    offset = cls._REPR.size + node_header.start_offset
    #loads all index entries related to the root node
    while True:
        entry = IndexEntry.create_from_binary(binary_stream[offset:], attr_type)
        index_entry_list.append(entry)
        if entry.flags & IndexEntryFlags.LAST_ENTRY:
            break
        else:
            offset += len(entry)

    nw_obj = cls((attr_type, CollationRule(collation_rule), b_per_idx_r,
                    c_per_idx_r, node_header, index_entry_list ))

    _MOD_LOGGER.debug("Attempted to unpack INDEX_ROOT Entry from \"%s\"\nResult: %s", binary_stream.tobytes(), nw_obj)

    return nw_obj

def _len_idx_root(self):
    return IndexRoot._REPR.size


_docstring_idx_root = '''Represents the content of a INDEX_ROOT attribute.

The structure of an index is a B+ tree, as such an root is always present.

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (:obj:`AttrTypes`): Attribute type
    content[1] (:obj:`CollationRule`): Collation rule
    content[2] (int): Index record size in bytes
    content[3] (int): Index record size in clusters
    node_header (IndexNodeHeader) - Node header related to this index root
    idx_entry_list (list(IndexEntry))- List of index entries that belong to
        this index root

Attributes:
    attr_type (:obj:`AttrTypes`): Attribute type
    collation_rule (:obj:`CollationRule`): Collation rule
    index_len_in_bytes (int): Index record size in bytes
    index_len_in_cluster (int): Index record size in clusters
    node_header (IndexNodeHeader): Node header related to this index root
    index_entry_list (list(IndexEntry)): List of index entries that belong to
'''

_idx_root_namespace = {"__len__" : _len_idx_root,
                    "create_from_binary" : classmethod(_from_binary_idx_root)
                 }

IndexRoot = _create_attrcontent_class("IndexRoot",
            ("attr_type", "collation_rule", "index_len_in_bytes", "index_len_in_cluster",
             "node_header", "index_entry_list"),
        inheritance=(AttributeContentRepr,), data_structure="<3IB3x",
        extra_functions=_idx_root_namespace, docstring=_docstring_idx_root)

#******************************************************************************
# BITMAP ATTRIBUTE
#******************************************************************************

def _allocated_entries_bitmap(self):
    '''Creates a generator that returns all allocated entries in the
    bitmap.

    Yields:
        int: The bit index of the allocated entries.

    '''
    for entry_number in range(len(self._bitmap) * 8):
        if self.entry_allocated(entry_number):
            yield entry_number

def _entry_allocated_bitmap(self, entry_number):
    """Checks if a particular index is allocated.

    Args:
        entry_number (int): Index to verify

    Returns:
        bool: True if it is allocated, False otherwise.
    """
    index, offset = divmod(entry_number, 8)
    return bool(self._bitmap[index] & (1 << offset))

def _get_next_empty_bitmap(self):
    """Returns the next empty entry.

    Returns:
        int: The value of the empty entry
    """
    #TODO probably not the best way, redo
    for i, byte in enumerate(self._bitmap):
        if byte != 255:
            for offset in range(8):
                if not byte & (1 << offset):
                    return (i * 8) + offset

def _from_binary_bitmap(cls, binary_stream):
    """See base class."""
    return cls(binary_stream.tobytes())

def _len_bitmap(self):
    '''Returns the size of the bitmap in bytes'''
    return len(self._bitmap)

_docstring_bitmap = """Represents the content of a BITMAP attribute.

Correctly represents a bitmap as seen by the MFT. That basically means that
the underlying data structure is interpreted bit by bit, where if the bit
is 1, the entry is "occupied"/allocated.


Args:
    binary_data (:obj:`bytes`): The bytes where the data is maintained
"""

_bitmap_namespace = {"__len__" : _len_bitmap,
                     "get_next_empty" : _get_next_empty_bitmap,
                     "entry_allocated" : _entry_allocated_bitmap,
                     "allocated_entries" : _allocated_entries_bitmap,
                     "create_from_binary" : classmethod(_from_binary_bitmap)
                 }

Bitmap = _create_attrcontent_class("Bitmap",
            ("_bitmap", ),
        inheritance=(AttributeContentNoRepr,), data_structure=None,
        extra_functions=_bitmap_namespace, docstring=_docstring_bitmap)

#******************************************************************************
# REPARSE_POINT ATTRIBUTE
#******************************************************************************

def _from_binary_junc_mnt(cls, binary_stream):
    """See base class."""
    ''' Offset to target name - 2 (relative to 16th byte)
        Length of target name - 2
        Offset to print name - 2 (relative to 16th byte)
        Length of print name - 2
    '''
    offset_target_name, len_target_name, offset_print_name, len_print_name = \
        cls._REPR.unpack(binary_stream[:cls._REPR.size])

    offset = cls._REPR.size + offset_target_name
    target_name = binary_stream[offset:offset+len_target_name].tobytes().decode("utf_16_le")
    offset = cls._REPR.size + offset_print_name
    print_name = binary_stream[offset:offset+len_print_name].tobytes().decode("utf_16_le")

    nw_obj = cls((target_name, print_name))

    _MOD_LOGGER.debug("Attempted to unpack Junction or MNT point from \"%s\"\nResult: %s", binary_stream.tobytes(), nw_obj)

    return nw_obj

def _len_junc_mnt(self):
    '''Returns the size of the bitmap in bytes'''
    return len(self.target_name.encode("utf_16_le")) + len(self.print_nameencode("utf_16_le"))  + 4 #size of offsets

_docstring_junc_mnt = """Represents the content of a REPARSE_POINT attribute when it is a junction
or mount point.

Args:
    target_name (str): Target name
    print_name (str): Print name

Attributes:
    target_name (str): Target name
    print_name (str): Print name
"""

_junc_mnt_namespace = {"__len__" : _len_junc_mnt,
                    "create_from_binary" : classmethod(_from_binary_junc_mnt)
                 }

JunctionOrMount = _create_attrcontent_class("JunctionOrMount",
            ("target_name", "print_name"),
        inheritance=(AttributeContentRepr,), data_structure="<4H",
        extra_functions=_junc_mnt_namespace, docstring=_docstring_junc_mnt)

#------------------------------------------------------------------------------

def _from_binary_syn_link(cls, binary_stream):
    """See base class."""
    ''' Offset to target name - 2 (relative to 16th byte)
        Length of target name - 2
        Offset to print name - 2 (relative to 16th byte)
        Length of print name - 2
        Symbolic link flags - 4
    '''
    offset_target_name, len_target_name, offset_print_name, \
    len_print_name, syn_flags = \
        cls._REPR.unpack(binary_stream[:cls._REPR.size])

    offset = cls._REPR.size + offset_target_name
    target_name = binary_stream[offset:offset+len_target_name].tobytes().decode("utf_16_le")
    offset = cls._REPR.size + offset_print_name
    print_name = binary_stream[offset:offset+len_print_name].tobytes().decode("utf_16_le")

    nw_obj = cls((target_name, print_name, SymbolicLinkFlags(syn_flags)))

    _MOD_LOGGER.debug("Attempted to unpack Symbolic Link from \"%s\"\nResult: %s", binary_stream.tobytes(), nw_obj)

    return nw_obj

def _len_syn_link(self):
    '''Returns the size of the bitmap in bytes'''
    return len(self.target_name.encode("utf_16_le")) + len(self.print_nameencode("utf_16_le"))  + 8 #size of offsets + flags

_docstring_syn_link = """Represents the content of a REPARSE_POINT attribute when it is a
symbolic link.

Args:
    target_name (str): Target name
    print_name (str): Print name
    sym_flags (:obj:`SymbolicLinkFlags`): Symbolic link flags

Attributes:
    target_name (str): Target name
    print_name (str): Print name
    sym_flags (:obj:`SymbolicLinkFlags`): Symbolic link flags
"""

_syn_link_namespace = {"__len__" : _len_syn_link,
                    "create_from_binary" : classmethod(_from_binary_syn_link)
                 }

SymbolicLink = _create_attrcontent_class("SymbolicLink",
            ("target_name", "print_name", "symbolic_flags"),
        inheritance=(AttributeContentRepr,), data_structure="<4HI",
        extra_functions=_syn_link_namespace, docstring=_docstring_junc_mnt)

#------------------------------------------------------------------------------

def _from_binary_reparse(cls, binary_stream):
    """See base class."""
    ''' Reparse type flags - 4
            Reparse tag - 4 bits
            Reserved - 12 bits
            Reparse type - 2 bits
        Reparse data length - 2
        Padding - 2
    '''
    #content = cls._REPR.unpack(binary_view[:cls._REPR.size])
    reparse_tag, data_len = cls._REPR.unpack(binary_stream[:cls._REPR.size])

    #reparse_tag (type, flags) data_len, guid, data
    reparse_type = ReparseType(reparse_tag & 0x0000FFFF)
    reparse_flags = ReparseFlags((reparse_tag & 0xF0000000) >> 28)
    guid = None #guid exists only in third party reparse points
    if reparse_flags & ReparseFlags.IS_MICROSOFT:#a microsoft tag
        if reparse_type is ReparseType.SYMLINK:
            data = SymbolicLink.create_from_binary(binary_stream[cls._REPR.size:])
        elif reparse_type is ReparseType.MOUNT_POINT:
            data = JunctionOrMount.create_from_binary(binary_stream[cls._REPR.size:])
        else:
            data = binary_stream[cls._REPR.size:].tobytes()
    else:
        guid = UUID(bytes_le=binary_stream[cls._REPR.size:cls._REPR.size+16].tobytes())
        data = binary_stream[cls._REPR.size+16:].tobytes()

    nw_obj = cls((reparse_type, reparse_flags, data_len, guid, data))

    _MOD_LOGGER.debug("Attempted to unpack REPARSE_POINT from \"%s\"\nResult: %s", binary_stream.tobytes(), nw_obj)

    return nw_obj

def _len_reparse(self):
    '''Returns the size of the bitmap in bytes'''
    return ReparsePoint._REPR.size + self.data_len

_docstring_reparse = '''Represents the content of a REPARSE_POINT attribute.

The REPARSE_POINT attribute is a little more complicated. We can have
Microsoft predefinied content and third-party content. As expected,
this completely changes how the data is interpreted.

All Microsoft types of REPARSE_POINT can be gathered from the winnt.h file.
However, as of now, only two have been implemented:

    * Symbolic Links - SYMLINK
    * Mount or junction point - MOUNT_POINT

As for third-party data, this is always saved in raw (bytes).

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (:obj:`ReparseType`): Reparse point type
    content[1] (:obj:`ReparseFlags`): Reparse point flags
    content[2] (int): Reparse data length
    content[3] (:obj:`UUID`): GUID
    content[4] (*variable*): Content of the reparse type

Attributes:
    reparse_type (:obj:`ReparseType`): Reparse point type
    reparse_flags (:obj:`ReparseFlags`): Reparse point flags
    data_len (int): Reparse data length
    guid (:obj:`UUID`): GUID. This exists only in the third-party
        reparse points. If it is a Microsoft one, it defaults to ``None``
    data (*variable*): Content of the reparse type
'''

_reparse_namespace = {"__len__" : _len_reparse,
                    "create_from_binary" : classmethod(_from_binary_reparse)
                 }

ReparsePoint = _create_attrcontent_class("ReparsePoint",
            ("reparse_type", "reparse_flags", "data_len", "guid", "data"),
        inheritance=(AttributeContentRepr,), data_structure="<IH2x",
        extra_functions=_reparse_namespace, docstring=_docstring_reparse)

#******************************************************************************
# EA_INFORMATION ATTRIBUTE
#******************************************************************************

def _from_binary_ea_info(cls, binary_stream):
    """See base class."""
    ''' Size of Extended Attribute entry - 2
        Number of Extended Attributes which have NEED_EA set - 2
        Size of extended attribute data - 4
    '''
    return cls(cls._REPR.unpack(binary_stream[:cls._REPR.size]))

def _len_ea_info(self):
    return EaInformation._REPR.size

_docstring_ea_info = '''Represents the content of a EA_INFORMATION attribute.

The (HPFS) extended attribute information ($EA_INFORMATION) contains
information about the extended attribute ($EA).

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (int): Size of the EA attribute entry
    content[1] (int): Number of EA attributes with NEED_EA set
    content[2] (int): Size of the EA data

Attributes:
    entry_len (int): Size of the EA attribute entry
    ea_set_number (int): Number of EA attributes with NEED_EA set
    ea_size (int): Size of the EA data
'''

_ea_info_namespace = {"__len__" : _len_ea_info,
                    "create_from_binary" : classmethod(_from_binary_ea_info)
                 }

EaInformation = _create_attrcontent_class("EaInformation",
            ("entry_len", "ea_set_number", "ea_size"),
        inheritance=(AttributeContentRepr,), data_structure="<2HI",
        extra_functions=_ea_info_namespace, docstring=_docstring_ea_info)

#******************************************************************************
# EA ATTRIBUTE
#******************************************************************************

def _from_binary_ea_entry(cls, binary_stream):
    """See base class."""
    ''' Offset to the next EA  - 4
        Flags - 1
        Name length - 1
        Value length - 2
    '''
    offset_next_ea, flags, name_len, value_len = cls._REPR.unpack(binary_stream[:cls._REPR.size])

    name = binary_stream[cls._REPR.size:cls._REPR.size + name_len].tobytes().decode("ascii")
    #it looks like the value is 8 byte aligned, do some math to compensate
    #TODO confirm if this is true
    value_alignment = (_ceil((cls._REPR.size + name_len) / 8) * 8)
    value = binary_stream[value_alignment:value_alignment + value_len].tobytes()

    nw_obj = cls((offset_next_ea, EAFlags(flags), name, value))

    _MOD_LOGGER.debug("Attempted to unpack EA entry from \"%s\"\nResult: %s", binary_stream.tobytes(), nw_obj)

    return nw_obj

def _len_ea_entry(self):
    '''Returns the size of the entry'''
    return EaEntry._REPR.size + len(self.name.encode("ascii")) + self.value_len

_docstring_ea_entry = '''Represents an entry for EA.

The EA attribute is composed by multiple EaEntries. Some information is not
completely understood for this. One of those is if it is necessary some
kind of aligment from the name to the value. The code considers a 8 byte
aligment and calculates that automatically.

Warning:
    The interpretation of the binary data MAY be wrong. The community does
    not have all the data.

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (int): Offset to the next EA
    content[1] (:obj:`EAFlags`): Changed timestamp
    content[2] (str): Name of the EA attribute
    content[3] (bytes): Value of the attribute

Attributes:
    offset_next_ea (int): Offset to next extended attribute entry.
        The offset is relative from the start of the extended attribute data.
    flags (:obj:`EAFlags`): Changed timestamp
    name (str): Name of the EA attribute
    value (bytes): Value of the attribute
'''

_ea_entry_namespace = {"__len__" : _len_ea_entry,
                    "create_from_binary" : classmethod(_from_binary_ea_entry)
                 }

EaEntry = _create_attrcontent_class("EaEntry",
            ("offset_next_ea", "flags", "name", "value"),
        inheritance=(AttributeContentRepr,), data_structure="<I2BH",
        extra_functions=_ea_entry_namespace, docstring=_docstring_ea_entry)

#------------------------------------------------------------------------------

def _from_binary_ea(cls, binary_stream):
    """See base class."""
    _ea_list = []
    offset = 0

    #_MOD_LOGGER.debug(f"Creating Ea object from binary stream {binary_stream.tobytes()}...")
    _MOD_LOGGER.debug("Creating Ea object from binary '%s'...", binary_stream.tobytes())
    while True:
        entry = EaEntry.create_from_binary(binary_stream[offset:])
        offset += entry.offset_next_ea
        _ea_list.append(entry)
        if offset >= len(binary_stream):
            break
    nw_obj = cls(_ea_list)

    _MOD_LOGGER.debug("Attempted to unpack EA from \"%s\"\nResult: %s", binary_stream.tobytes(), nw_obj)

    return nw_obj

def _len_ea(self):
    '''Return the number of entries in the attribute list'''
    return len(self._attr_list)

def _iter_ea(self):
    return iter(self._attr_list)

def _gitem_ea(self, index):
    return _getitem(self._attr_list, index)

_docstring_ea = '''Represents the content of a EA attribute.

Is a list of EaEntry. It behaves as list in python, you can iterate
over it, access by member, etc.

Important:
    Using the ``len()`` method on the objects of this class returns the number
    of elements in the list.

Args:
    content (list(:obj:`EaEntry`)): List of AttributeListEntry
'''

_ea_namespace = {"__len__" : _len_ea,
                       "__iter__" : _iter_ea,
                       "__getitem__" : _gitem_ea,
                       "create_from_binary" : classmethod(_from_binary_ea)
                 }

Ea = _create_attrcontent_class("Ea",
            ("_ea_list",),
        inheritance=(AttributeContentNoRepr,), data_structure=None,
        extra_functions=_ea_namespace, docstring=_docstring_ea)

#******************************************************************************
# SECURITY_DESCRIPTOR ATTRIBUTE
#******************************************************************************

def _from_binary_secd_header(cls, binary_stream):
    """See base class."""
    ''' Revision number - 1
        Padding - 1
        Control flags - 2
        Reference to the owner SID - 4 (offset relative to the header)
        Reference to the group SID - 4 (offset relative to the header)
        Reference to the DACL - 4 (offset relative to the header)
        Reference to the SACL - 4 (offset relative to the header)
    '''
    nw_obj = cls(cls._REPR.unpack(binary_stream))
    nw_obj.control_flags = SecurityDescriptorFlags(nw_obj.control_flags)

    _MOD_LOGGER.debug("Attempted to unpack Security Descriptor Header from \"%s\"\nResult: %s", binary_stream.tobytes(), nw_obj)

    return nw_obj

def _len_secd_header(self):
    '''Returns the logical size of the file'''
    return SecurityDescriptorHeader._REPR.size

_docstring_secd_header = '''Represents the header of the SECURITY_DESCRIPTOR attribute.

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (int): Revision number
    content[1] (:obj:`SecurityDescriptorFlags`): Control flags
    content[2] (int): Offset to the owner SID
    content[3] (int): Offset to the group SID
    content[4] (int): Offset to the DACL
    content[5] (int): Offset to the SACL

Attributes:
    revision_number (int): Revision number
    control_flags (:obj:`SecurityDescriptorFlags`): Control flags
    owner_sid_offset (int): Offset to the owner SID
    group_sid_offset (int): Offset to the group SID
    dacl_offset (int): Offset to the DACL
    sacl_offset (int): Offset to the SACL
'''

_secd_header_namespace = {"__len__" : _len_secd_header,
                    "create_from_binary" : classmethod(_from_binary_secd_header)
                 }

SecurityDescriptorHeader = _create_attrcontent_class("SecurityDescriptorHeader",
            ("revision_number", "control_flags", "owner_sid_offset",
                "group_sid_offset", "dacl_offset", "sacl_offset"),
        inheritance=(AttributeContentRepr,), data_structure="<B1xH4I",
        extra_functions=_secd_header_namespace, docstring=_docstring_secd_header)

#------------------------------------------------------------------------------

def _from_binary_ace_header(cls, binary_stream):
    """See base class."""
    ''' ACE Type - 1
        ACE Control flags - 1
        Size - 2 (includes header size)
    '''
    type, control_flags, size = cls._REPR.unpack(binary_stream)
    nw_obj = cls((ACEType(type), ACEControlFlags(control_flags), size))

    _MOD_LOGGER.debug("Attempted to unpack ACE Header from \"%s\"\nResult: %s", binary_stream.tobytes(), nw_obj)

    return nw_obj

def _len_ace_header(self):
    '''Returns the logical size of the file'''
    return ACEHeader._REPR.size

_docstring_ace_header = '''Represents header of an ACE object.

As part of the an ACL, all ACE (Access Control Entry) have a header that
is represented by this class.

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (:obj:`ACEType`): Type of ACE entry
    content[1] (:obj:`ACEControlFlags`): ACE control flags
    content[2] (int): size of the ACE entry, including the header

Attributes:
    type (:obj:`ACEType`): Type of ACE entry
    control_flags (:obj:`ACEControlFlags`): ACE control flags
    ace_size (int): size of the ACE entry, including the header
'''

_ace_header_namespace = {"__len__" : _len_ace_header,
                    "create_from_binary" : classmethod(_from_binary_ace_header)
                 }

ACEHeader = _create_attrcontent_class("ACEHeader",
            ("type", "control_flags", "ace_size"),
        inheritance=(AttributeContentRepr,), data_structure="<2BH",
        extra_functions=_ace_header_namespace, docstring=_docstring_ace_header)

#-------------------------------------------------------------------------------

def _from_binary_sid(cls, binary_stream):
    """See base class."""
    ''' Revision number - 1
        Number of sub authorities - 1
        Authority - 6
        Array of 32 bits with sub authorities - 4 * number of sub authorities
    '''
    rev_number, sub_auth_len, auth = cls._REPR.unpack(binary_stream[:cls._REPR.size])
    if sub_auth_len:
        sub_auth_repr = struct.Struct("<" + str(sub_auth_len) + "I")
        sub_auth = sub_auth_repr.unpack(binary_stream[cls._REPR.size:cls._REPR.size + sub_auth_repr.size])
    else:
        sub_auth = ()

    nw_obj = cls((rev_number, int.from_bytes(auth, byteorder="big"), sub_auth))

    _MOD_LOGGER.debug("Attempted to unpack SID from \"%s\"\nResult: %s", binary_stream.tobytes(), nw_obj)

    return nw_obj

def _len_sid(self):
    '''Returns the size of the SID in bytes'''
    return SID._REPR.size + (4 * sub_auth_len)

def _str_sid(self):
    'Return a nicely formatted representation string'
    sub_auths = "-".join([str(sub) for sub in self.sub_authorities])
    return f'S-{self.revision_number}-{self.authority}-{sub_auths}'

_docstring_sid = '''Represents the content of a SID object to be used by the SECURITY_DESCRIPTOR
attribute.

This represents a Microsoft SID, normally seen as::

    S-1-5-21-7623811015-3361044348-030300820-1013

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (int): Revision number
    content[1] (int): Number of sub authorities
    content[2] (int): Authority
    sub_authorities (list(int)): List of sub authorities

Attributes:
    revision_number (int): Revision number
    authority (int): Authority
    sub_authorities (list(int)): List of sub authorities
'''

_sid_namespace = {"__len__" : _len_sid,
                    "create_from_binary" : classmethod(_from_binary_sid),
                    "__str__" : _str_sid
                 }

SID = _create_attrcontent_class("SID",
            ("revision_number", "authority", "sub_authorities"),
        inheritance=(AttributeContentRepr,), data_structure="<2B6s",
        extra_functions=_sid_namespace, docstring=_docstring_sid)

#-------------------------------------------------------------------------------

def _from_binary_b_ace(cls, binary_stream):
    """See base class."""
    ''' Access rights flags - 4
        SID - n
    '''
    access_flags = cls._REPR.unpack(binary_stream[:cls._REPR.size])[0]
    sid = SID.create_from_binary(binary_stream[cls._REPR.size:])

    nw_obj = cls((ACEAccessFlags(access_flags), sid))

    return nw_obj

def _len_b_ace(self):
    '''Returns the logical size of the file'''
    return BasicACE._REPR.size

_docstring_b_ace = '''Represents one the types of ACE entries. The Basic type.

The Basic ACE is a very simple entry that contains the access flags for a
particular SID.

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (:obj:`ACEAccessFlags`): Access rights flags
    content[1] (:obj:`SID`): SID

    self.access_rights_flags, self.sid

Attributes:
    access_rights_flags (:obj:`ACEAccessFlags`): Access rights flags
    sid (:obj:`SID`): SID
'''

_b_ace_namespace = {"__len__" : _len_b_ace,
                    "create_from_binary" : classmethod(_from_binary_b_ace)
                 }

BasicACE = _create_attrcontent_class("BasicACE",
            ("access_rights_flags", "SID"),
        inheritance=(AttributeContentRepr,), data_structure="<I",
        extra_functions=_b_ace_namespace, docstring=_docstring_b_ace)

#-------------------------------------------------------------------------------

def _from_binary_obj_ace(cls, binary_stream):
    """See base class."""
    ''' Access rights flags - 4
        Flags - 4
        Object type class identifier (GUID) - 16
        Inherited object type class identifier (GUID) - 16
        SID - n
    '''
    #content = cls._REPR.unpack(binary_stream[:cls._REPR.size])
    access_flags, flags, object_guid, inher_guid = cls._REPR.unpack(binary_stream[:cls._REPR.size])
    sid = SID.create_from_binary(binary_stream[cls._REPR.size:])

    nw_obj = cls((ACEAccessFlags(access_flags),flags, UUID(bytes_le=object_guid), UUID(bytes_le=inher_guid), sid))

    return nw_obj

def _len_obj_ace(self):
    '''Returns the logical size of the file'''
    return ObjectACE._REPR.size + len(self.sid)

_docstring_obj_ace = '''Represents one the types of ACE entries. The Object type.

This is a more complex type of ACE that contains the access flags, a group
of undocumented flags, the object id and its inherited object id and the SID
where it is applicable.

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (:obj:`ACEAccessFlags`): Access rights flags
    content[1] (int): Flags
    content[2] (:obj:`UUID`): Object type class identifier (GUID)
    content[3] (:obj:`UUID`): Inherited object type class identifier (GUID)
    content[4] (:obj:`SID`): SID

Attributes:
    access_rights_flags (:obj:`ACEAccessFlags`): Access rights flags
    flags (int): Flags
    object_guid (:obj:`UUID`): Object type class identifier (GUID)
    inherited_guid (:obj:`UUID`): Inherited object type class identifier (GUID)
    sid (:obj:`SID`): SID
'''

_obj_ace_namespace = {"__len__" : _len_b_ace,
                    "create_from_binary" : classmethod(_from_binary_b_ace)
                 }

ObjectACE = _create_attrcontent_class("ObjectACE",
            ("access_rights_flags", "flags", "object_guid", "inherited_guid", "sid"),
        inheritance=(AttributeContentRepr,), data_structure="<2I16s16s",
        extra_functions=_obj_ace_namespace, docstring=_docstring_obj_ace)

#-------------------------------------------------------------------------------

class CompoundACE():
    '''Nobody knows this structure'''
    pass

#-------------------------------------------------------------------------------

def _from_binary_ace(cls, binary_stream):
    nw_obj = cls()
    header = ACEHeader.create_from_binary(binary_stream[:cls._HEADER_SIZE])

    nw_obj.header = header

    #TODO create a _dispatcher and replace this slow ass comparison
    if "OBJECT" in header.type.name:
        nw_obj.object_ace = ObjectACE.create_from_binary(binary_stream[cls._HEADER_SIZE:])
    elif "COMPOUND" in header.type.name:
        pass
    else:
        nw_obj.basic_ace = BasicACE.create_from_binary(binary_stream[cls._HEADER_SIZE:])

    return nw_obj

def _len_ace(self):
    '''Returns the logical size of the file'''
    return self.header.ace_size

_docstring_ace = '''Represents an ACE object.

This class aggregates all the information about an ACE (Access Control Entry).
Its header, if it is an Object or Basic ACE.

Important:
    The class should never have both basic ace and object ace attributes.

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (:obj:`ACEHeader`): Created timestamp
    content[1] (:obj:`BasicACE`): Changed timestamp
    content[2] (:obj:`ObjectACE`): MFT change timestamp

Attributes:
    header (:obj:`ACEHeader`): Created timestamp
    basic_ace (:obj:`BasicACE`): Changed timestamp
    object_ace (:obj:`ObjectACE`): MFT change timestamp
'''

_ace_namespace = {"__len__" : _len_ace,
                  "create_from_binary" : classmethod(_from_binary_ace),
                  "_HEADER_SIZE" : ACEHeader.get_representation_size(),
                 }

ACE = _create_attrcontent_class("ACE",
            ("header", "basic_ace", "object_ace"),
        inheritance=(AttributeContentNoRepr,), data_structure=None,
        extra_functions=_ace_namespace, docstring=_docstring_ace)

#-------------------------------------------------------------------------------

def _from_binary_acl(cls, binary_stream):
    """See base class."""
    ''' Revision number - 1
        Padding - 1
        Size - 2
        ACE Count - 2
        Padding - 2
    '''
    rev_number, size, ace_len = cls._REPR.unpack(binary_stream[:cls._REPR.size])
    #content = cls._REPR.unpack(binary_stream[:cls._REPR.size])
    aces = []

    offset = cls._REPR.size
    for i in range(ace_len):
        ace = ACE.create_from_binary(binary_stream[offset:])
        offset += len(ace)
        aces.append(ace)
        _MOD_LOGGER.debug("Next ACE offset = %d", offset)
    nw_obj = cls((rev_number, size, aces))

    _MOD_LOGGER.debug("Attempted to unpack SID from \"%s\"\nResult: %s", binary_stream.tobytes(), nw_obj)

    return nw_obj

def _len_acl(self):
    '''Returns the logical size of the file'''
    return self.size

_docstring_acl = '''Represents an ACL for the SECURITY_DESCRIPTOR.

Represents a Access Control List (ACL), which contains multiple ACE entries.

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (:obj:`datetime`): Revision number
    content[1] (int): Size
    content[2] (int): Number of ACE entries
    aces (list(:obj:`ACE`)): MFT change timestamp

Attributes:
    revision_number[0] (:obj:`datetime`): Revision number
    size (int): Size
    aces (list(:obj:`ACE`)): MFT change timestamp
'''

_acl_namespace = {"__len__" : _len_acl,
                    "create_from_binary" : classmethod(_from_binary_acl)
                 }

ACL = _create_attrcontent_class("ACL",
            ("revision_number", "size", "aces"),
        inheritance=(AttributeContentRepr,), data_structure="<B1x2H2x",
        extra_functions=_acl_namespace, docstring=_docstring_acl)

#-------------------------------------------------------------------------------

def _from_binary_sec_desc(cls, binary_stream):
    """See base class."""
    header = SecurityDescriptorHeader.create_from_binary(binary_stream[:SecurityDescriptorHeader.get_representation_size()])

    owner_sid = SID.create_from_binary(binary_stream[header.owner_sid_offset:])
    group_sid = SID.create_from_binary(binary_stream[header.group_sid_offset:])
    dacl = None
    sacl = None

    if header.sacl_offset:
        sacl = ACL.create_from_binary(binary_stream[header.sacl_offset:])
    if header.dacl_offset:
        dacl = ACL.create_from_binary(binary_stream[header.dacl_offset:])

    nw_obj = cls((header, owner_sid, group_sid, sacl, dacl))
    
    return nw_obj


def _len_sec_desc(self):
    '''Returns the logical size of the file'''
    return len(self.header) + len(self.owner_sid) + len(self.group_sid) + len(self.sacl) + len(self.dacl)

_docstring_sec_desc = '''Represents the content of a SECURITY_DESCRIPTOR attribute.

The Security Descriptor in Windows has a header, an owner SID and group SID, plus a
discretionary access control list (DACL) and a system access control list (SACL).

Both DACL and SACL are ACLs with the same format.

Note:
    This class receives an Iterable as argument, the "Parameters/Args" section
    represents what must be inside the Iterable. The Iterable MUST preserve
    order or things might go boom.

Args:
    content[0] (:obj:`SecurityDescriptorHeader`): Created timestamp
    content[1] (:obj:`SID`): Changed timestamp
    content[2] (:obj:`SID`): MFT change timestamp
    content[3] (:obj:`ACL`): Accessed timestamp
    content[4] (:obj:`ACL`): Accessed timestamp

Attributes:
    header (:obj:`SecurityDescriptorHeader`): Created timestamp
    owner_sid (:obj:`SID`): Changed timestamp
    group_sid (:obj:`SID`): MFT change timestamp
    sacl (:obj:`ACL`): Accessed timestamp
    dacl (:obj:`ACL`): Accessed timestamp
'''

_sec_desc_namespace = {"__len__" : _len_sec_desc,
                    "create_from_binary" : classmethod(_from_binary_sec_desc)
                 }

SecurityDescriptor = _create_attrcontent_class("SecurityDescriptor",
            ("header", "owner_sid", "group_sid", "sacl", "dacl"),
        inheritance=(AttributeContentNoRepr,),
        extra_functions=_sec_desc_namespace, docstring=_docstring_sec_desc)

#******************************************************************************
# LOGGED_TOOL_STREAM ATTRIBUTE
#******************************************************************************
class LoggedToolStream():
    #TODO implement the know cases of this attribute
    def __init__(self, bin_view):
        '''Initialize the class. Expects the binary_view that represents the
        content. Size information is derived from the content.
        '''
        self.content = bin_view.tobytes()

    def __repr__(self):
        'Return a nicely formatted representation string'
        return self.__class__.__name__ + '(content={})'.format(
            self.content)
