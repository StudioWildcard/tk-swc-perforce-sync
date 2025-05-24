# Copyright (c) 2015 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

from collections import defaultdict
from sgtk.platform.qt import QtCore, QtGui

import sgtk
import datetime
from . import utils, constants
from . import model_item_data

logger = sgtk.platform.get_logger(__name__)

# import the shotgun_model module from the shotgun utils framework
shotgun_model = sgtk.platform.import_framework(
    "tk-swc-framework-shotgunutils", "shotgun_model"
)
ShotgunModel = shotgun_model.ShotgunModel

class SgLatestPublishModel(ShotgunModel):
    """
    Model which handles the main spreadsheet view which displays the latest version of all
    publishes.

    All images returned by this model will be 512x400 pixels.
    """

    TYPE_ID_ROLE = QtCore.Qt.UserRole + 101
    IS_FOLDER_ROLE = QtCore.Qt.UserRole + 102
    ASSOCIATED_TREE_VIEW_ITEM_ROLE = QtCore.Qt.UserRole + 103
    PUBLISH_TYPE_NAME_ROLE = QtCore.Qt.UserRole + 104
    SEARCHABLE_NAME = QtCore.Qt.UserRole + 105

    def __init__(self, parent, publish_type_model, bg_task_manager):
        """
        Model which represents the latest publishes for an entity
        """
        self._publish_type_model = publish_type_model
        self._folder_icon = QtGui.QIcon(QtGui.QPixmap(":/res/folder_512x400.png"))
        self._loading_icon = QtGui.QIcon(QtGui.QPixmap(":/res/loading_512x400.png"))
        self._perforce_icon = QtGui.QIcon(QtGui.QPixmap(":/res/perforce_1.png"))
        self._associated_items = {}

        app = sgtk.platform.current_bundle()

        # init base class
        ShotgunModel.__init__(
            self,
            parent,
            download_thumbs=app.get_setting("download_thumbnails"),
            schema_generation=6,
            bg_load_thumbs=True,
            bg_task_manager=bg_task_manager,
        )

    ############################################################################################
    # public interface

    def get_associated_tree_view_item(self, item):
        """
        Returns the entity tree view item associated with a publish folder item.

        :returns: item or None if not found.
        """
        entity_item_hash = item.data(self.ASSOCIATED_TREE_VIEW_ITEM_ROLE)
        return self._associated_items.get(entity_item_hash)

    def load_data(self, item, child_folders, show_sub_items, additional_sg_filters):
        """
        Clears the model and sets it up for a particular entity.
        Loads any cached data that exists.

        :param item: Selected item in the treeview, None if nothing is selected.
        :param child_folders: List of items ('folders') from the tree view.
        :param show_sub_items: Indicates whether to use sub items mode.
        :param additional_sg_filters: List of Shotgun filters to add to the query.
        """
        app = sgtk.platform.current_bundle()
        sg_data = {}
        data_type = None

        if item is None:
            sg_filters = None
        else:
            if show_sub_items:
                model_idx = item.index()
                model = model_idx.model()
                partial_filters = model.get_filters(item)
                entity_type = model.get_entity_type()
                data = app.shotgun.find(entity_type, partial_filters)
                if entity_type == "Task":
                    sg_filters = [["task", "in", data]]
                elif entity_type == "Version":
                    sg_filters = [["version", "in", data]]
                else:
                    sg_filters = [["entity", "in", data]]
                data_type = entity_type
                child_folders = []
            else:
                (sg_data, field_value) = model_item_data.get_item_data(item)
                if sg_data:
                    data_type = sg_data.get("type", None)
                    if sg_data.get("type") == "Task":
                        sg_filters = [
                            ["task", "is", {"type": sg_data["type"], "id": sg_data["id"]}]
                        ]
                    elif sg_data.get("type") == "Version":
                        sg_filters = [
                            ["version", "is", {"type": "Version", "id": sg_data["id"]}]
                        ]
                    else:
                        sg_filters = [
                            ["entity", "is", {"type": sg_data["type"], "id": sg_data["id"]}]
                        ]
                else:
                    if isinstance(field_value, dict) and "name" in field_value and "type" in field_value:
                        sg_filters = [["entity", "is", field_value]]
                    else:
                        sg_filters = None

        if sg_filters:
            pub_filters = app.get_setting("publish_filters", [])
            sg_filters.extend(pub_filters)
            sg_filters.extend(additional_sg_filters)

        if data_type in ["Asset", "Shot", "Task"]:
            self._do_load_data(sg_filters, child_folders, sg_data_type=data_type)
        else:
            self._do_load_data(sg_filters, child_folders)

        return sg_data

    def async_refresh(self):
        """
        Refresh the current data set
        """
        self._refresh_data()

    def _set_tooltip(self, item, sg_item):
        """
        Sets a tooltip for this model item.
        """
        tooltip = "<b>Name:</b> %s" % (sg_item.get("code") or "No name given.")
        published_file_type = sg_item.get('type', None)
        if published_file_type in ['PublishedFile']:
            if not isinstance(sg_item.get("created_at"), datetime.datetime):
                created_unixtime = sg_item.get("created_at") or 0
                date_str = datetime.datetime.fromtimestamp(created_unixtime).strftime(
                    "%Y-%m-%d %H:%M"
                )
            else:
                date_str = sg_item.get("created_at").strftime("%Y-%m-%d %H:%M")
            author_str = sg_item["created_by"].get("name") if sg_item.get("created_by") and sg_item["created_by"].get("name") else "Unspecified User"
            version = sg_item.get("version_number")
            vers_str = "%03d" % version if version is not None else "N/A"
            tooltip += "<br><br><b>Version:</b> %s by %s at %s" % (vers_str, author_str, date_str)
        tooltip += "<br><br><b>Path:</b> %s" % ((sg_item.get("path") or {}).get("local_path"))
        tooltip += "<br><br><b>Description:</b> %s" % (sg_item.get("description") or "No description given.")
        tooltip += "<br><br><b>Revision:</b> #%s" % (sg_item.get("revision") or "N/A")
        if sg_item.get("headAction"):
            tooltip += "<br><br><b>Head action:</b> %s" % (sg_item.get("headAction") or "N/A")
        if sg_item.get("headChange"):
            tooltip += "<br><br><b>Head change:</b> %s" % (sg_item.get("headChange") or "N/A")
        if sg_item.get("change"):
            tooltip += "<br><br><b>Change:</b> %s" % (sg_item.get("change") or "N/A")
        if sg_item.get("action"):
            tooltip += "<br><br><b>Action:</b> %s" % (sg_item.get("action") or "N/A")
        if sg_item.get("entity"):
            entity = sg_item.get("entity")
            if entity:
                entity_name = entity.get("name", "N/A")
                tooltip += "<br><br><b>Entity:</b> %s" % entity_name
                entity_id = entity.get("id", "N/A")
                tooltip += "<br><br><b>Entity ID:</b> %s" % entity_id
        item.setToolTip(tooltip)

    ############################################################################################
    # private methods

    def _do_load_data(self, sg_filters, treeview_folder_items, sg_data_type=None):
        """
        Load and refresh data.
        """
        app = sgtk.platform.current_bundle()
        publish_entity_type = sgtk.util.get_published_file_entity_type(app.tank)
        if publish_entity_type == "PublishedFile":
            self._publish_type_field = "published_file_type"
        else:
            self._publish_type_field = "tank_type"
        publish_fields = [self._publish_type_field] + constants.PUBLISHED_FILES_FIELDS
        self._treeview_folder_items = treeview_folder_items
        ShotgunModel._load_data(
            self,
            entity_type=publish_entity_type,
            filters=sg_filters,
            hierarchy=["code"],
            fields=publish_fields,
            order=[{"field_name": "created_at", "direction": "asc"}],
            sg_data_type=sg_data_type
        )
        self._refresh_data()

    ############################################################################################
    # subclassed methods

    def _load_external_data(self):
        """
        Called to add folder items to the model.
        """
        self._folder_items = []
        self._associated_items = {}
        for tree_view_item in self._treeview_folder_items:
            tree_view_item_hash = str(id(tree_view_item))
            item = shotgun_model.ShotgunStandardItem(self._folder_icon, tree_view_item.text())
            item.setData(tree_view_item.text(), SgLatestPublishModel.SEARCHABLE_NAME)
            item.setData(True, SgLatestPublishModel.IS_FOLDER_ROLE)
            item.setData(tree_view_item_hash, SgLatestPublishModel.ASSOCIATED_TREE_VIEW_ITEM_ROLE)
            (tree_view_sg_data, field_value) = model_item_data.get_item_data(tree_view_item)
            tree_view_field_data = {"value": field_value}
            item.setData(tree_view_sg_data, SgLatestPublishModel.SG_DATA_ROLE)
            item.setData(tree_view_field_data, SgLatestPublishModel.SG_ASSOCIATED_FIELD_ROLE)
            if tree_view_sg_data and tree_view_sg_data.get("image"):
                self._request_thumbnail_download(
                    item, "image", tree_view_sg_data["image"], tree_view_sg_data["type"], tree_view_sg_data["id"]
                )
            self.appendRow(item)
            self._folder_items.append(item)
            self._associated_items[tree_view_item_hash] = tree_view_item

    def _populate_item(self, item, sg_data):
        """
        Populate item with metadata.
        """
        item.setData(False, SgLatestPublishModel.IS_FOLDER_ROLE)
        search_str = ""
        type_link = sg_data.get(self._publish_type_field)
        if type_link:
            item.setData(type_link["id"], SgLatestPublishModel.TYPE_ID_ROLE)
            item.setData(type_link["name"], SgLatestPublishModel.PUBLISH_TYPE_NAME_ROLE)
            search_str += "%s " % type_link["name"]
        else:
            item.setData(None, SgLatestPublishModel.TYPE_ID_ROLE)
            item.setData("No Type", SgLatestPublishModel.PUBLISH_TYPE_NAME_ROLE)
            try:
                source = sg_data.get("source", None)
                if source in ["Perforce"]:
                    file_type_name = sg_data.get("file_type_name", None)
                    if file_type_name:
                        details_text = "<span style='color:rgb(140, 0, 0)'>  #%s  </span>" % file_type_name
                        item.setData(details_text, SgLatestPublishModel.PUBLISH_TYPE_NAME_ROLE)
            except Exception as e:
                logger.debug("Error setting file_type_name: {}".format(e))
        if sg_data.get("name"):
            search_str += " %s" % sg_data["name"]
        if sg_data.get("version_number"):
            search_str += " v%03d" % sg_data["version_number"]
        item.setData(search_str, SgLatestPublishModel.SEARCHABLE_NAME)

    def _populate_default_thumbnail(self, item):
        """
        Set default thumbnail.
        """
        item.setIcon(self._loading_icon)

    def _populate_thumbnail_image(self, item, field, image, path):
        """
        Apply thumbnail to item.
        """
        try:
            if field != "image":
                return
            is_folder = item.data(SgLatestPublishModel.IS_FOLDER_ROLE)
            if is_folder:
                thumb = utils.create_overlayed_folder_thumbnail(image)
            else:
                thumb = utils.create_overlayed_publish_thumbnail(image)
            item.setIcon(QtGui.QIcon(thumb))
        except:
            pass

    def _before_data_processing(self, sg_data_list):
        """
        Filter publishes to keep only the latest version per file and compute type aggregates.
        """
        app = sgtk.platform.current_bundle()
        sg_data_list = utils.filter_publishes(app, sg_data_list)
        if len(sg_data_list) == 0 and len(self._treeview_folder_items) == 0:
            self._publish_type_model.set_active_types([])
            return []

        # Filter to keep only the highest version_number per path.local_path
        file_version_map = defaultdict(list)
        for sg_item in sg_data_list:
            local_path = sg_item.get("path", {}).get("local_path")
            if local_path:
                file_version_map[local_path].append(sg_item)
            else:
                file_version_map[None].append(sg_item)

        unique_data = {}
        name_type_aggregates = defaultdict(int)
        for local_path, items in file_version_map.items():
            if len(items) > 1 and local_path:
                highest_version_item = max(
                    items,
                    key=lambda x: x.get("version_number", 0),
                    default=items[0]
                )
                unique_data[local_path] = highest_version_item
            else:
                for item in items:
                    unique_data[local_path or item["id"]] = item

        # Compute aggregates and task uniqueness
        type_id_aggregates = []
        for sg_item in unique_data.values():
            type_id = None
            type_link = sg_item.get(self._publish_type_field)
            if type_link:
                type_id = type_link["id"]
                if type_id not in type_id_aggregates:
                    type_id_aggregates.append(type_id)
            task_id = None
            task_link = sg_item.get("task")
            if task_link:
                task_id = task_link["id"]
            depot_file = sg_item.get("sg_p4_depo_path")
            key = (sg_item["name"], type_id, task_id, depot_file)
            name_type_aggregates[(sg_item["name"], type_id)] += 1

        # Set task uniqueness flag
        new_sg_data = []
        for sg_item in unique_data.values():
            type_id = sg_item.get(self._publish_type_field, {}).get("id")
            if name_type_aggregates[(sg_item["name"], type_id)] > 1:
                sg_item["task_uniqueness"] = False
            else:
                sg_item["task_uniqueness"] = True
            new_sg_data.append(sg_item)

        self._publish_type_model.set_active_types(type_id_aggregates)
        return new_sg_data