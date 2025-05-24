# Copyright (c) 2015 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import sgtk
from sgtk.platform.qt import QtCore, QtGui

# import the shotgun_model module from the shotgun utils framework
shotgun_model = sgtk.platform.import_framework(
    "tk-swc-framework-shotgunutils", "shotgun_model"
)
ShotgunModel = shotgun_model.ShotgunModel

class SgPublishTypeModel(ShotgunModel):
    """
    This model holds all the publish types. It is connected to the filter UI where
    a user can choose which items to display.

    The model loads all publish type data from shotgun and then culls out values
    not applicable to the current actions setup - basically, only types corresponding
    to the actions that have been configured will show up - nuke scripts wont show up in
    maya and vice versa. The model also handles duplicate values, (which is more common
    with the old tank publish type which were per project).
    """

    SORT_KEY_ROLE = QtCore.Qt.UserRole + 102  # holds a sortable key
    DISPLAY_NAME_ROLE = QtCore.Qt.UserRole + 103  # holds the display name for the node

    FOLDERS_ITEM_TEXT = "Folders"

    def __init__(self, parent, action_manager, settings_manager, bg_task_manager):
        """
        Constructor
        """
        ShotgunModel.__init__(
            self,
            parent,
            download_thumbs=False,
            schema_generation=2,
            bg_load_thumbs=True,
            bg_task_manager=bg_task_manager,
        )
        self._log = sgtk.LogManager.get_logger(self.__class__.__name__)
        self._action_manager = action_manager
        self._settings_manager = settings_manager

        # specify sort key
        self.setSortRole(SgPublishTypeModel.SORT_KEY_ROLE)

        # now set up the model.
        # first figure out which fields to get from shotgun
        app = sgtk.platform.current_bundle()
        publish_entity_type = sgtk.util.get_published_file_entity_type(app.sgtk)

        if publish_entity_type == "PublishedFile":
            publish_type_field = "PublishedFileType"
        else:
            publish_type_field = "TankType"

        # get previous sessions selection
        self._deselected_pub_types = self._settings_manager.retrieve(
            "deselected_pub_types_v2", [], self._settings_manager.SCOPE_INSTANCE
        )

        # note: this model encodes which publish types are currently
        # supported by the running engine. Basically what this means is that the
        # model data holds a combination of shotgun data (the publish types) and
        # the action_mappings configuration parameter. We therefore need to pass
        # an external cache seed to the query and this seed is based on the current
        # action mappings - whenever these change, the cache data is also affected.
        mappings_str = str(app.get_setting("action_mappings"))

        ShotgunModel._load_data(
            self,
            entity_type=publish_type_field,
            filters=[],
            hierarchy=["code"],
            fields=["code", "id"],
            seed=mappings_str,
        )

        # and finally ask model to refresh itself
        self._refresh_data()

    def destroy(self):
        """
        Destructor
        """
        # save filter settings
        val = []
        for idx in range(self.rowCount()):
            item = self.item(idx)
            if item.checkState() == QtCore.Qt.Unchecked:
                # this item is not checked. Store its publish id
                sg_data = shotgun_model.get_sg_data(item)
                val.append(sg_data.get("code"))

        self._settings_manager.store(
            "deselected_pub_types_v2", val, self._settings_manager.SCOPE_INSTANCE
        )

        # call base class
        ShotgunModel.destroy(self)

    def select_none(self):
        """
        Deselect all types
        """
        for idx in range(self.rowCount()):
            item = self.item(idx)
            # ignore special case folders item
            if item.text() != SgPublishTypeModel.FOLDERS_ITEM_TEXT:
                item.setCheckState(QtCore.Qt.Unchecked)

    def select_all(self):
        """
        Select all types
        """
        for idx in range(self.rowCount()):
            item = self.item(idx)
            item.setCheckState(QtCore.Qt.Checked)

    def get_show_folders(self):
        """
        Returns true if the special Folders
        entry is ticked, false otherwise
        """
        for idx in range(self.rowCount()):
            item = self.item(idx)
            # ignore special case folders item
            if item.text() != SgPublishTypeModel.FOLDERS_ITEM_TEXT:
                continue
            if item.checkState() == QtCore.Qt.Checked:
                return True
        return False

    def get_selected_types(self):
        """
        Returns all the sg type ids that are currently selected.

        :returns: a list of type ids (ints)
        """
        type_ids = []
        for idx in range(self.rowCount()):
            item = self.item(idx)
            # ignore special case folders item
            if item.text() == SgPublishTypeModel.FOLDERS_ITEM_TEXT:
                continue
            if item.checkState() == QtCore.Qt.Checked:
                # get the shotgun id
                associated_sg_ids = shotgun_model.get_sg_data(item).get("ids", [])
                if not associated_sg_ids:
                    self._log.warning(f"No 'ids' found in Shotgun data for item: {shotgun_model.get_sg_data(item)}")
                type_ids.extend(associated_sg_ids)
        return type_ids

    def set_active_types(self, type_id_aggregates):
        """
        Specifies which types are currently active. Also adjust the sort role,
        so that the view puts enabled items at the top of the list!

        :param type_id_aggregates: List of publish type IDs present in the publish data.
        """
        for idx in range(self.rowCount()):
            item = self.item(idx)
            # ignore special folders item
            if item.text() == SgPublishTypeModel.FOLDERS_ITEM_TEXT:
                continue
            # get list of shotgun publish type ids associated with this
            sg_data = shotgun_model.get_sg_data(item)
            sg_type_ids = sg_data.get("ids", [])
            if not sg_type_ids:
                self._log.warning(f"No 'ids' found in Shotgun data for item: {sg_data}")
                item.setEnabled(False)
                item.setText(f"{sg_data.get('code', 'Unnamed')} (0)")
                item.setData(f"b_{sg_data.get('code', 'Unnamed')}", SgPublishTypeModel.SORT_KEY_ROLE)
                continue
            display_name = shotgun_model.get_sanitized_data(item, self.DISPLAY_NAME_ROLE)
            # count matches between item's ids and aggregates
            total_matches = sum(1 for type_id in sg_type_ids if str(type_id) in [str(agg_id) for agg_id in type_id_aggregates])
            if total_matches > 0:
                # there are matches for this publish type
                item.setData(f"a_{display_name}", SgPublishTypeModel.SORT_KEY_ROLE)
                item.setEnabled(True)
                item.setText(f"{display_name} ({total_matches})")
            else:
                # this type is not found in the list of current matches
                item.setEnabled(False)
                item.setData(f"b_{display_name}", SgPublishTypeModel.SORT_KEY_ROLE)
                item.setText(f"{display_name} (0)")
        # ask the model to resort itself
        self.sort(0)

    def hard_refresh(self):
        """
        Clears any caches on disk, then refreshes the data.
        """
        super(SgPublishTypeModel, self).hard_refresh()
        self._load_external_data()

    ############################################################################################
    # subclassed methods

    def _load_external_data(self):
        """
        Called whenever the model needs to be rebuilt from scratch.
        """
        self._folder_items = []
        item = shotgun_model.ShotgunStandardItem(SgPublishTypeModel.FOLDERS_ITEM_TEXT)
        item.setCheckable(True)
        item.setCheckState(QtCore.Qt.Checked)
        item.setToolTip(
            "This filter controls the <i>folder objects</i>. "
            "If you are using the 'Show items in subfolders' mode, it can "
            "sometimes be useful to hide folders and only see publishes."
        )
        self.appendRow(item)
        self._folder_items.append(item)

    def _before_data_processing(self, sg_data_list):
        """
        Cull out irrelevant publish types and collapse duplicates.
        """
        sg_data_handled_types = {}
        for sg_data in sg_data_list:
            sg_code = sg_data.get("code")
            if self._action_manager.has_actions(sg_code):
                if sg_code in sg_data_handled_types:
                    sg_data_handled_types[sg_code]["ids"].append(sg_data["id"])
                else:
                    sg_data_handled_types[sg_code] = sg_data
                    sg_data_handled_types[sg_code]["ids"] = [sg_data["id"]]
        return list(sg_data_handled_types.values())

    def _finalize_item(self, item):
        """
        Called whenever an item is fully constructed.
        """
        item.setEnabled(False)
        sg_data = item.get_sg_data()
        if sg_data and sg_data.get("code") not in self._deselected_pub_types:
            item.setCheckState(QtCore.Qt.Checked)
        else:
            item.setCheckState(QtCore.Qt.Unchecked)

    def _populate_item(self, item, sg_data):
        """
        Populate item with metadata.
        """
        sg_code = sg_data.get("code")
        if sg_code is None:
            sg_name_formatted = "Unnamed"
        else:
            sg_name_formatted = sg_code
        item.setData(sg_name_formatted, SgPublishTypeModel.DISPLAY_NAME_ROLE)
        item.setCheckable(True)