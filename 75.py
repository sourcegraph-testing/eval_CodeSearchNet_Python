# Copyright 2015 Michael Frank <msfrank@syntaxjockey.com>
#
# This file is part of cifparser.  cifparser is BSD-licensed software;
# for copyright information see the LICENSE file.

import datetime
import re

from cifparser.errors import ConversionError

def str_to_stripped(s):
    return s.strip()

def str_to_flattened(s):
    return ' '.join(s.split())

def str_to_int(s):
    try:
        return int(s)
    except:
        raise ConversionError("failed to convert {0} to float".format(s))

def str_to_bool(s):
    s = s.lower()
    if s in ('true', 'yes', '1'):
        return True
    if s in ('false', 'no', '0'):
        return False
    raise ConversionError("failed to convert {0} to bool".format(s))

def str_to_float(s):
    try:
        return float(s)
    except:
        raise ConversionError("failed to convert {0} to float".format(s))

def str_to_timedelta(s):
    s = s.strip()
    try:
        m = re.match(r'([1-9]\d*)\s*(.*)', s)
        if m is None:
            raise Exception("{0} did not match regex".format(s))
        value = int(m.group(1))
        units = m.group(2).lower().strip()
        if units in ('us', 'micro', 'micros', 'microsecond', 'microseconds'):
            return datetime.timedelta(microseconds=value)
        if units in ('ms', 'milli', 'millis', 'millisecond', 'milliseconds'):
            return datetime.timedelta(milliseconds=value)
        if units in ('s', 'second', 'seconds'):
            return datetime.timedelta(seconds=value)
        if units in ('m', 'minute', 'minutes'):
            return datetime.timedelta(minutes=value)
        if units in ('h', 'hour', 'hours'):
            return datetime.timedelta(hours=value)
        if units in ('d', 'day', 'days'):
            return datetime.timedelta(days=value)
        if units in ('w', 'week', 'weeks'):
            return datetime.timedelta(weeks=value)
    except Exception as e:
        raise ConversionError("failed to convert {0} to timedelta".format(s))

def str_to_size(s):
    s = s.strip()
    try:
        m = re.match(r'(0|[1-9]\d*)\s*(.*)', s)
        if m is None:
            raise Exception("{0} did not match regex".format(s))
        value = int(m.group(1))
        units = m.group(2).lower().strip()
        if units in ('b', 'byte', 'bytes'):
            return value
        if units in ('kb', 'kilo', 'kilobyte', 'kilobytes'):
            return value * 1024
        if units in ('mb', 'mega', 'megabyte', 'megabytes'):
            return value * 1024 * 1024
        if units in ('gb', 'giga', 'gigabyte', 'gigabytes'):
            return value * 1024 * 1024 * 1024
        if units in ('tb', 'tera', 'terabyte', 'terabytes'):
            return value * 1024 * 1024 * 1024 * 1024
        if units in ('pb', 'peta', 'petabyte', 'petabytes'):
            return value * 1024 * 1024 * 1024 * 1024 * 1024
    except Exception as e:
        raise ConversionError("failed to convert {0} to size in bytes".format(s))

def str_to_percentage(s):
    s = s.strip()
    try:
        m = re.match(r'(0?\.\d+|[1-9]\d*\.\d+|\d+)\s*%', s)
        if m is None:
            raise Exception("{0} did not match regex".format(s))
        return float(m.group(1)) / 100.0
    except Exception as e:
        raise ConversionError("failed to convert {0} to percentage".format(s))

def str_to_throughput(s):
    s = s.strip()
    try:
        m = re.match(r'(0?\.\d+|[1-9]\d*\.\d+|\d+)\s*(.*)', s)
        if m is None:
            raise Exception("{0} did not match regex".format(s))
        value = float(m.group(1))
        units = m.group(2).strip()
        if units in ('bps', 'Bps', 'bytes/s', 'bytes/sec', 'bytes/second'):
            return value
        if units in ('Kbps', 'kilobytes/s', 'kilobytes/sec', 'kilobytes/second'):
            return value * 1024.0
        if units in ('Mbps', 'megabytes/s', 'megabytes/sec', 'megabytes/second'):
            return value * 1024.0 * 1024.0
        if units in ('Gbps', 'gigabytes/s', 'gigabytes/sec', 'gigabytes/second'):
            return value * 1024.0 * 1024.0 * 1024.0
        if units in ('Tbps', 'terabytes/s', 'terabytes/sec', 'terabytes/second'):
            return value * 1024.0 * 1024.0 * 1024.0 * 1024.0
        if units in ('Pbps', 'petabytes/s', 'petabytes/sec', 'petabytes/second'):
            return value * 1024.0 * 1024.0 * 1024.0 * 1024.0 * 1024.0
    except Exception as e:
        raise ConversionError("failed to convert {0} to size in bytes".format(s))
