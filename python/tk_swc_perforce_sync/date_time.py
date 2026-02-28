# Copyright (c) 2016 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import datetime
from tank_vendor import shotgun_api3
import sgtk
logger = sgtk.platform.get_logger(__name__)


def create_modified_date(dt):
    """
    Return the date represented by the argument as a string, displaying recent
    dates as "Today", "This Week", "This Month", or "Older".

    :param dt: The date to convert to a string. Can be a UNIX timestamp (float),
               a :class:`datetime.date`, or a :class:`datetime.datetime` object.
    :type dt: float, :class:`datetime.date`, or :class:`datetime.datetime`

    :returns: A String representing date appropriate for display
    """
    if isinstance(dt, float):  # Check if dt is a UNIX timestamp
        dt = datetime.datetime.fromtimestamp(dt)  # Convert UNIX timestamp to datetime

    now = datetime.datetime.now(dt.tzinfo if isinstance(dt, datetime.datetime) else None)
    today = now.date()

    if isinstance(dt, datetime.datetime):
        dt = dt.date()  # convert datetime to date for comparison

    delta = today - dt

    if delta.days == 0:
        date_str = "Today"
    elif delta.days <= 7:
        date_str = "This Week"
    elif delta.days <= 30:
        date_str = "This Month"
    else:
        date_str = "Older"

    return date_str


def create_human_readable_date(dt):
    """
    Return the date represented by the argument as a string, displaying recent
    dates as "Yesterday", "Today", or "Tomorrow".

    :param dt: The date convert to a string
    :type dt: :class:`datetime.date` or :class:`datetime.datetime`

    :returns: A String representing date appropriate for display
    """
    delta, date_str = None, None
    if isinstance(dt, datetime.datetime):
        delta = datetime.datetime.now(dt.tzinfo) - dt
    elif isinstance(dt, datetime.date):
        delta = datetime.date.today() - dt

    if delta:
        if delta.days == 1:
            date_str = "Yesterday"
        elif delta.days == 0:
            date_str = "Today"
        elif delta.days == -1:
            date_str = "Tomorrow"
        else:
            # use the locale appropriate date representation
            date_str = dt.strftime("%x")

    return date_str


def create_human_readable_timestamp(dt):
    created_unixtime = int(dt)

    date_str = datetime.datetime.fromtimestamp(
        created_unixtime, shotgun_api3.sg_timezone.LocalTimezone()
    )
    return date_str


def create_publish_timestamp(dt):
    created_unixtime = int(dt)

    date_str = datetime.datetime.fromtimestamp(created_unixtime).strftime(
        "%m-%d-%y %H:%M:%S"
    )

    return date_str


def get_time_now():
    date_str = datetime.datetime.now()
    return date_str
