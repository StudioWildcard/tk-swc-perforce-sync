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
EntityBrowser — owns entity detail panels, parent/children tabs,
breadcrumbs, entity path resolution, and filesystem structure operations.

Extracted from dialog.py as Phase 3, Step 4 of the P4SG cleanup.

Note: _load_entity_presets, _recreate_entity_presets, and
_on_treeview_item_selected remain on AppDialog because they deeply
orchestrate multiple manager interactions and widget state.
"""

import os

import sgtk
from sgtk.platform.qt import QtCore, QtGui

# Import Qt classes into module namespace (mirrors dialog.py pattern)
for _name, _cls in QtCore.__dict__.items():
    if isinstance(_cls, type):
        globals()[_name] = _cls
for _name, _cls in QtGui.__dict__.items():
    if isinstance(_cls, type):
        globals()[_name] = _cls

from . import model_item_data

logger = sgtk.platform.get_logger(__name__)

shotgun_globals = sgtk.platform.import_framework(
    "tk-swc-framework-shotgunutils", "shotgun_globals"
)


class EntityBrowser(QtCore.QObject):
    """
    Manages entity detail panels, parent/children tabs, breadcrumbs,
    entity path resolution, and filesystem structure operations.
    """

    log_message = QtCore.Signal(str, int)

    def __init__(self, app, ui, sync_manager, parent=None):
        super(EntityBrowser, self).__init__(parent)
        self._app = app
        self.ui = ui
        self._sync_manager = sync_manager

    # -----------------------------------------------------------------------
    # Entity info / path resolution
    # -----------------------------------------------------------------------

    def get_entity_info(self, entity_data):
        """
        Returns the filesystem path, entity ID, and entity type for an entity.
        """
        entity_path = None
        entity_id = None
        entity_type = None

        if entity_data:
            entity_id = entity_data.get("id", None)
            entity_type = entity_data.get("type", None)

            if entity_id and entity_type:
                try:
                    dirs = self._app.sgtk.paths_from_entity(entity_type, entity_id)
                except Exception as e:
                    dirs = None

                if dirs and len(dirs) > 0:
                    entity_path = dirs[0]

        return entity_path, entity_id, entity_type

    def get_entity_path(self, entity_data, entity_path=None):
        """
        Returns the filesystem path for an entity, using the existing path
        if available, or looking it up.
        """
        if not entity_path and entity_data:
            entity_id = entity_data.get("id", None)
            entity_type = entity_data.get("type", None)
            if entity_id and entity_type:
                try:
                    dirs = self._app.sgtk.paths_from_entity(entity_type, entity_id)
                    if dirs and len(dirs) > 0:
                        entity_path = dirs[0]
                except Exception as e:
                    pass
        return entity_path

    # -----------------------------------------------------------------------
    # Entity details panel
    # -----------------------------------------------------------------------

    def setup_entity_details_panel(self, entity_data, item):
        """
        Sets up the entity details panel with info for a given item.
        """
        def __make_table_row(left, right):
            return (
                "<tr><td><b style='color:#2C93E2'>%s</b>&nbsp;</td><td>%s</td></tr>"
                % (left, right)
            )

        if entity_data:
            entity_name = entity_data.get("code", None)
            entity_type = entity_data.get("type", None)
            entity_id = entity_data.get("id", None)
            for field in entity_data.keys():
                if "image" in field and entity_data[field] is not None:
                    image_url = entity_data.get(field)
                    logger.debug("Image url: %s" % image_url)
                    thumb_pixmap = QPixmap.fromImage(image_url)
                    self.ui.entity_details_image.setPixmap(thumb_pixmap)

            msg = ""
            if entity_name:
                msg += __make_table_row("Name", "%s" % entity_name)
            if entity_type:
                msg += __make_table_row("Type", "%s" % entity_type)
            if entity_id:
                msg += __make_table_row("ID", "%s" % entity_id)

            entity_status = entity_data.get("sg_status_list", None)
            if entity_status:
                msg += __make_table_row("Status", "%s" % entity_status)
            entity_description = entity_data.get("description", None)
            if entity_description:
                msg += __make_table_row("Description", "%s" % entity_description)
            entity_asset_type = entity_data.get("sg_asset_type", None)
            if entity_asset_type:
                msg += __make_table_row("Asset Type", "%s" % entity_asset_type)

            self.ui.entity_details_text.setText("<table>%s</table>" % msg)

    # -----------------------------------------------------------------------
    # Entity parents / children
    # -----------------------------------------------------------------------

    def get_entity_parents(self, entity_data):
        """Get parent entities for an entity."""
        entity_parents = []
        if entity_data:
            entity_type = entity_data.get("type", None)
            entity_id = entity_data.get("id", None)
            if entity_type and entity_id:
                try:
                    parent = self._app.shotgun.find_one(
                        entity_type,
                        [["id", "is", entity_id]],
                        ["sg_asset_parent"]
                    )
                    if parent:
                        parent_entity = parent.get("sg_asset_parent", None)
                        if parent_entity:
                            entity_parents.append(parent_entity)
                            # Recursively get parents
                            grandparents = self.get_entity_parents(parent_entity)
                            entity_parents.extend(grandparents)
                except Exception as e:
                    logger.debug("Error getting entity parents: {}".format(e))
        return entity_parents

    def setup_entity_parent_and_children(self, entity_data):
        """Set up the entity parent and children tabs."""
        if entity_data:
            entity_type = entity_data.get("type", None)
            entity_id = entity_data.get("id", None)
            if entity_type and entity_id:
                parents = self.get_entity_parents(entity_data)
                children = self._get_entity_children(entity_data)
                self.populate_parents_tab(parents)
                self.populate_children_tab(children)

    def _get_entity_children(self, entity_data):
        """Get child entities for an entity."""
        entity_children = []
        if entity_data:
            entity_type = entity_data.get("type", None)
            entity_id = entity_data.get("id", None)
            if entity_type and entity_id:
                try:
                    children = self._app.shotgun.find(
                        entity_type,
                        [["sg_asset_parent", "is", {"type": entity_type, "id": entity_id}]],
                        ["code", "sg_status_list", "sg_asset_type", "id", "type", "image"]
                    )
                    if children:
                        entity_children = children
                except Exception as e:
                    logger.debug("Error getting entity children: {}".format(e))
        return entity_children

    def populate_parents_tab(self, parents):
        """Populate the parents tab with parent entity data."""
        # Clear existing content
        while self.ui.entity_parents_layout.count():
            item = self.ui.entity_parents_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if parents:
            for parent in parents:
                if parent:
                    parent_name = parent.get("name", None) or parent.get("code", None)
                    parent_type = parent.get("type", None)
                    parent_id = parent.get("id", None)
                    if parent_name:
                        label = QLabel()
                        label.setText(
                            "<span style='color:#2C93E2'><b>{}</b></span> {} (ID: {})".format(
                                parent_type or "", parent_name, parent_id or ""
                            )
                        )
                        label.setTextFormat(Qt.RichText)
                        self.ui.entity_parents_layout.addWidget(label)
        else:
            label = QLabel("No parent entities found.")
            self.ui.entity_parents_layout.addWidget(label)

        self.ui.entity_parents_layout.addStretch()

    def populate_children_tab(self, children):
        """Populate the children tab with child entity data."""
        # Clear existing content
        while self.ui.entity_children_layout.count():
            item = self.ui.entity_children_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if children:
            for child in children:
                if child:
                    child_name = child.get("code", None)
                    child_type = child.get("type", None)
                    child_id = child.get("id", None)
                    child_status = child.get("sg_status_list", None)
                    if child_name:
                        label = QLabel()
                        label.setText(
                            "<span style='color:#2C93E2'><b>{}</b></span> {} (Status: {})".format(
                                child_type or "", child_name, child_status or "N/A"
                            )
                        )
                        label.setTextFormat(Qt.RichText)
                        self.ui.entity_children_layout.addWidget(label)
        else:
            label = QLabel("No child entities found.")
            self.ui.entity_children_layout.addWidget(label)

        self.ui.entity_children_layout.addStretch()

    # -----------------------------------------------------------------------
    # Breadcrumbs
    # -----------------------------------------------------------------------

    def populate_entity_breadcrumbs(self, selected_item, current_entity_preset):
        """
        Computes the current entity breadcrumbs.

        :param selected_item: Item currently selected in the tree view or
                              `None` when no selection has been made.
        :param current_entity_preset: Name of the current entity preset tab.
        """
        crumbs = []

        if selected_item:
            tmp_item = selected_item
            while tmp_item:
                (sg_data, field_value) = model_item_data.get_item_data(tmp_item)

                if sg_data:
                    name = str(field_value)
                    sg_type = sg_data.get("type")
                elif (
                    isinstance(field_value, dict)
                    and "name" in field_value
                    and "type" in field_value
                ):
                    name = field_value["name"]
                    sg_type = field_value["type"]
                elif isinstance(field_value, list):
                    formatted_values = []
                    if len(field_value) == 0:
                        formatted_values.append("No Value")
                    for v in field_value:
                        if isinstance(v, dict) and "name" in v and "type" in v:
                            if v.get("name"):
                                formatted_values.append(v.get("name"))
                        else:
                            formatted_values.append(str(v))
                    name = ", ".join(formatted_values)
                    sg_type = None
                else:
                    name = str(field_value)
                    sg_type = None

                if sg_type is None:
                    crumbs.append(name)
                else:
                    sg_type_display_name = shotgun_globals.get_type_display_name(sg_type)
                    crumbs.append("<b>%s</b> %s" % (sg_type_display_name, name))
                tmp_item = tmp_item.parent()

        crumbs.append("<b>%s</b>" % current_entity_preset)

        breadcrumbs = " <span style='color:#2C93E2'>&#9656;</span> ".join(crumbs[::-1])
        self.ui.entity_breadcrumbs.setText("<big>%s</big>" % breadcrumbs)

    # -----------------------------------------------------------------------
    # Filesystem structure
    # -----------------------------------------------------------------------

    def create_filesystem_structure(self, entity_data, add_log_fn):
        """Create filesystem structure for an entity."""
        if entity_data:
            entity_type = entity_data.get("type", None)
            entity_id = entity_data.get("id", None)
            entity_name = entity_data.get("code", None) or entity_data.get("name", None)

            if entity_type and entity_id:
                try:
                    add_log_fn(
                        "\n <span style='color:#2C93E2'>Creating filesystem structure for {} {}...</span> \n".format(
                            entity_type, entity_name or entity_id
                        ), 2
                    )
                    self._app.sgtk.create_filesystem_structure(
                        entity_type, entity_id
                    )
                    add_log_fn(
                        "\n <span style='color:#2C93E2'>Filesystem structure created successfully.</span> \n", 2
                    )
                except Exception as e:
                    add_log_fn(
                        "\n <span style='color:#CC3333'>Error creating filesystem structure: {}</span> \n".format(e), 2
                    )
                    raise

    def preview_filesystem_structure(self, entity_data, add_log_fn):
        """Preview filesystem structure for an entity."""
        if entity_data:
            entity_type = entity_data.get("type", None)
            entity_id = entity_data.get("id", None)

            if entity_type and entity_id:
                try:
                    folders = self._app.sgtk.preview_filesystem_structure(
                        entity_type, entity_id
                    )
                    if folders:
                        add_log_fn(
                            "\n <span style='color:#2C93E2'>Folders that would be created:</span> \n", 2
                        )
                        for folder in folders:
                            add_log_fn("  {}".format(folder), 4)
                    else:
                        add_log_fn(
                            "\n <span style='color:#2C93E2'>No new folders would be created.</span> \n", 2
                        )
                    return folders
                except Exception as e:
                    add_log_fn(
                        "\n <span style='color:#CC3333'>Error previewing filesystem structure: {}</span> \n".format(e), 2
                    )
        return []

    def handle_folder_creation(self, entity_data, add_log_fn):
        """Handle folder creation with confirmation dialog."""
        if entity_data:
            entity_type = entity_data.get("type", None)
            entity_id = entity_data.get("id", None)
            entity_name = entity_data.get("code", None) or entity_data.get("name", None)

            if entity_type and entity_id:
                reply = QMessageBox.question(
                    self.parent(),
                    'Create Folders',
                    'Create filesystem structure for {} {}?'.format(
                        entity_type, entity_name or entity_id
                    ),
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self.create_filesystem_structure(entity_data, add_log_fn)
                    return True
        return False
