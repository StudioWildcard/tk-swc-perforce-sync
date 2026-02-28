# Copyright (c) 2013 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

"""
Common utilities for working with Perforce changes
"""
#from P4 import P4Exception

from sgtk import TankError, LogManager

log = LogManager.get_logger(__name__)
import sgtk
logger = sgtk.platform.get_logger(__name__)

def create_change(p4, description):
    """
    Helper method to create a new change
    """

    # create a new changelist:
    new_change = None
    try:
        # fetch a new change, update the description, and save it:
        change_spec = p4.fetch_change()
        change_spec._description = str(description)
        # have to clear the file list as otherwise it would contain everything
        # in the default changelist!
        change_spec._files = []
        p4_res = p4.save_change(change_spec)

        if p4_res:
            try:
                # p4_res should be like: ["Change 25 created."]
                new_change_id = int(p4_res[0].split()[1])
                new_change = str(new_change_id)
            except ValueError:
                raise TankError("Perforce: Failed to extract new change id from '%s'" % p4_res)
    except Exception as e:
        msg = "Perforce: %s" % (p4.errors[0] if p4.errors else e)
        log.debug(msg)

    if new_change == None:
        raise TankError("Perforce: Failed to create new change!")

    return new_change

import shutil
import os


def add_to_change(p4, change, file_paths):
    """
    Add the specified files to the specified change
    """
    add_res = None
    try:
        # use reopen command which works with local file paths.
        # fetch/modify/save_change only works with depot paths!
        add_res = p4.run_reopen("-c", str(change), file_paths)
        # add_res = p4.run_edit("-c", str(change), file_paths)

    except Exception as e:

        msg = "Error adding files {} to changelist: {}, error: {}".format(file_paths, file_paths, e)
        logger.debug(msg)
    return add_res

def add_depotfiles_to_change(p4, change, depot_file_paths):
    """
    Add the specified depot files to the specified change
    """
    add_res = None
    try:
        # Use fetch command to add depot files to the changelist
        add_res = p4.run_fetch("-c", str(change), depot_file_paths)

    except Exception as e:
        msg = "Error adding depot files {} to changelist: {}, error: {}".format(depot_file_paths, change, e)
        logger.debug(msg)
    return add_res

def add_to_default_changelist(p4, file_paths):
    """
    Add the specified files to the specified change
    """
    # add the files to the default changelist

    add_res = None
    try:
        default_changelist = p4.fetch_change()
        msg = "default changelist:: %s" % (default_changelist)
        log.debug(msg)
        if not default_changelist:
            default_changelist = p4.save_change(default_changelist)
            msg = "Created default changelist:: %s" % (default_changelist)
            log.debug(msg)

        # Mark the file for delete in the default changelist
        #p4.run_edit('-c', default_changelist, '-d', file_path)

        # use reopen command which works with local file paths.
        # fetch/modify/save_change only works with depot paths!
        change = default_changelist.get("Change", None )
        if change:
            add_res = p4.run_reopen("-c", change, file_paths)
        #add_res = p4.run_reopen('-c', default_changelist,file_paths)
        # add_res = p4.run_edit("-c", str(change), file_paths)

    except:
        msg = "Perforce: %s" % (p4.errors[0] if p4.errors else e)
        log.debug(msg)
    #except P4Exception as e:
    #   raise TankError("Perforce: %s" % (p4.errors[0] if p4.errors else e))
    return add_res


def find_change_containing(p4, path):
    """
    Find the current change that the specified path is in.
    """
    p4_res = None
    try:
        p4_res = p4.run_fstat(path)
    except:
        msg = "Perforce: %s" % (p4.errors[0] if p4.errors else e)
        log.debug(msg)
    #except P4Exception as e:
    #    raise TankError("Perforce: %s" % (p4.errors[0] if p4.errors else e))

    change = p4_res[0].get("change")
    return change


def submit_change(p4, change, filelist):
    """
    Submit the specified change
    """
    try:
        change_spec = p4.fetch_change("-o", str(change))
        submit = p4.run_submit(change_spec, filelist)
        """
        run_submit returns a list of dicts, something like this:
        [{'change': '90', 'locked': '2'},
         "Possible string in here",
         {'action': 'edit',
          'depotFile': '//deva/Tool/ScorchedEarth/ToolCategory/ToolTestAsset/deva_ScorchedEarth_ToolTestAsset_concept.psd',
          'rev': '2'},
         {'action': 'edit',
          'depotFile': '//deva/Tool/ScorchedEarth/ToolCategory/ToolTestAsset/deva_ScorchedEarth_ToolTestAsset_concept_alt.psd',
          'rev': '4'},
         {'submittedChange': '90'}]
        """
        log.debug("Return of run_submit: {}".format(submit))
        return submit
    except:
        msg = "Perforce: %s" % (p4.errors[0] if p4.errors else e)
        log.debug(msg)

def submit_single_file(p4, change, filepath, action):
    """
    Submit the specified change and then completely delete the file in Perforce.
    """
    try:
        # Mark files for deletion
        p4.run(action, filepath)

        # Fetch the change
        change_spec = p4.fetch_change("-o", str(change))

        # Submit the change
        submit_res = p4.run_submit(change_spec)
        log.debug("Return of run_submit: {}".format(submit_res))


        return submit_res
    except Exception as e:
        msg = "Perforce: %s" % (p4.errors[0] if p4.errors else e)
        log.debug(msg)


def submit_and_delete_file(p4, change, filepath):
    """
    Submit the specified file deletion using the provided changelist or create a new one if the changelist is committed.
    """
    submit_result, msg = None, None  # Initialize as None
    try:
        # Fetch the existing changelist (using the passed 'change' argument)
        change_spec = p4.fetch_change(change)

        # Check if the changelist is committed
        if 'submittedChange' in change_spec:
            # If the changelist is already committed, create a new pending changelist
            log.debug("Changelist {} is committed. Creating a new pending changelist.".format(change))
            new_change_spec = p4.fetch_change()
            new_change_spec['Description'] = "Deleting file: {}".format(filepath)
            change = p4.save_change(new_change_spec)[0].split()[1]  # Extract the new changelist number

        # Mark files for deletion
        p4.run('delete', filepath)

        # Submit the changelist (either the new one or the original if not committed)
        submit_result = p4.run_submit('-c', change)

    except Exception as e:
        msg = "Perforce error: %s" % (p4.errors[0] if p4.errors else e)
        log.debug(msg)

    return submit_result, msg


def submit_and_delete_file_list(p4, change, filelist):
    """
    Submit the specified change and then completely delete the file in Perforce.
    """
    try:
        # Mark files for deletion
        for file in filelist:
            p4.run('delete', file)

        # Fetch the change
        change_spec = p4.fetch_change("-o", str(change))

        # Submit the change
        submit = p4.run_submit(change_spec)
        log.debug("Return of run_submit: {}".format(submit))

        # Obliterate the files to completely remove them from the depot
        # Never obliterate files, as it is a destructive operation
        # for file in filelist:
        #     p4.run('obliterate', '-y', file)

        return submit
    except Exception as e:
        msg = "Perforce: %s" % (p4.errors[0] if p4.errors else e)
        log.debug(msg)

def get_change_details(p4, changes):
    """
    Get the changes details for one or more changes

    :param p4:         The Perforce connection
    :param changes:    The list of changes to query Perforce for
    :returns dict:     A dictionary mapping each change to the details found
    """
    try:
        p4_res = p4.run_describe(changes)
    except:
        msg = "Perforce: %s" % (p4.errors[0] if p4.errors else e)
        log.debug(msg)
    #except P4Exception as e:
    #    raise TankError("Perforce: %s" % (p4.errors[0] if p4.errors else e))

    p4_res_lookup = {}
    for item in p4_res:
        change = item.get("change")
        if not change:
            continue
        p4_res_lookup[change] = item

    change_details = {}
    for change in changes:
        details = p4_res_lookup.get(change)
        change_details[change] = details

    return change_details
