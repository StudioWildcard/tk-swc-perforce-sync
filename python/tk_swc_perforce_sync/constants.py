# Copyright (c) 2015 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
Constants used by the loader.

"""

# fields to pull down for published files
PUBLISHED_FILES_FIELDS = [
    "name",
    "version_number",
    "image",
    "entity",
    "path",
    "sg_p4_depo_path",
    "description",
    "sg_status_list",
    "task",
    "task.Task.sg_status_list",
    "task.Task.due_date",
    "step",
    "task.Task.step.Step.code",
    "project",
    "task.Task.content",
    "created_by",
    "created_at",
    "version",  # note: not supported on TankPublishedFile so always None
    "version.Version.sg_status_list",
    "created_by.HumanUser.image",

]

# left hand side tree view search only kicks in
# after a certain number have been typed in.
TREE_SEARCH_TRIGGER_LENGTH = 2

# Mapping of file extensions to human-readable type names.
# Used for publish type detection and display across multiple views.
EXTENSION_TYPE_MAP = {
    "wire": "Alias File",
    "abc": "Alembic Cache",
    "max": "3dsmax Scene",
    "hrox": "NukeStudio Project",
    "hip": "Houdini Scene",
    "hipnc": "Houdini Scene",
    "hiplc": "Houdini Scene",
    "ma": "Maya Scene",
    "mb": "Maya Scene",
    "fbx": "Motion Builder FBX",
    "nk": "Nuke Script",
    "psd": "Photoshop Image",
    "psb": "Photoshop Image",
    "vpb": "VRED Scene",
    "vpe": "VRED Scene",
    "osb": "VRED Scene",
    "dpx": "Rendered Image",
    "exr": "Rendered Image",
    "tiff": "Texture",
    "tx": "Texture",
    "tga": "Texture",
    "dds": "Texture",
    "jpeg": "Image",
    "jpg": "Image",
    "mov": "Movie",
    "mp4": "Movie",
    "pdf": "PDF",
    "png": "Image File",
    "spp": "PhotoPlus Image",
    "ztl": "ZBrush Document",
    "json": "JSON File",
    "pkl": "Python Pickle",
    "aep": "Adobe After Effects",
    "webm": "WebM Format",
}

# Mapping of Perforce actions to normalized action names.
ACTION_MAP = {
    "add": "add",
    "move/add": "add",
    "delete": "delete",
    "edit": "edit",
}

# Mapping of Perforce actions to ShotGrid status codes.
STATUS_MAP = {
    "add": "p4add",
    "move/add": "p4add",
    "delete": "p4del",
    "edit": "p4edit",
}
