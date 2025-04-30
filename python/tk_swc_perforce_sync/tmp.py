def def _on_treeview_item_selected(self):
        """
        Slot triggered when someone changes the selection in a treeview.
        Resolves the correct entity for panel navigation, especially for Tasks.
        """
        logger.debug("Treeview item selection changed.")
        self._fstat_dict = {}  # Reset Perforce status

        # 1. Get the selected item from the tree view FIRST
        selected_item = self._get_selected_entity()

        # --- Early exit if nothing is selected ---
        if not selected_item:
            logger.debug("No item selected in the tree view.")
            # Clear dependent UI elements
            self._publish_model.clear()  # Clear publish view
            self._sg_data = []
            self._fstat_dict = {}
            self._entity_path = None
            self._entity_data = None  # Ensure this is None
            self._setup_file_details_panel([])  # Clear details panel
            QtCore.QTimer.singleShot(0, lambda: self._get_shotgun_panel_widget(None))  # Clear panel
            # Optionally clear column/submitted views if applicable
            if self.main_view_mode == self.MAIN_VIEW_COLUMN:
                self.column_view_model.setRowCount(0)
            if self.main_view_mode == self.MAIN_VIEW_SUBMITTED:
                self._reset_submitted_widget()
            return  # Stop processing

        # 2. Extract the core ShotGrid data directly from the selected item
        # model_item_data.get_item_data usually returns (sg_data, field_value)
        # sg_data is the full dict for leaf nodes (Assets, Shots)
        # field_value can be the entity dict for 'My Tasks' (Task entity)
        # Let's prioritize field_value if it's an entity dict, else use sg_data
        sg_data_from_tree, field_value_from_tree = model_item_data.get_item_data(selected_item)

        # Determine the primary entity data associated with the click
        # This handles both Asset/Shot clicks and Task clicks correctly
        entity_data_clicked = None
        if isinstance(field_value_from_tree, dict) and field_value_from_tree.get("type") and field_value_from_tree.get(
                "id"):
            entity_data_clicked = field_value_from_tree  # e.g., Task data from 'My Tasks'
            logger.debug(f"Using field_value as primary entity data: {entity_data_clicked}")
        elif isinstance(sg_data_from_tree, dict) and sg_data_from_tree.get("type") and sg_data_from_tree.get("id"):
            entity_data_clicked = sg_data_from_tree  # e.g., Asset data from 'Assets'
            logger.debug(f"Using sg_data as primary entity data: {entity_data_clicked}")
        else:
            logger.error(
                f"Could not extract valid entity data from selected tree item: sg_data={sg_data_from_tree}, field_value={field_value_from_tree}")
            # Handle error state - maybe clear UI? For now, log and return.
            return

        # Store this primary data (Asset, Shot, or Task)
        self._entity_data = entity_data_clicked  # THIS IS NOW RELIABLE

        # 3. Resolve the entity for Panel Navigation (Handles Tasks)
        target_entity_for_panel = None
        if self._entity_data:
            entity_type = self._entity_data.get("type")
            if entity_type == "Task":
                linked_entity = self._entity_data.get("entity")
                if linked_entity and isinstance(linked_entity, dict) and linked_entity.get("id") and linked_entity.get(
                        "type"):
                    target_entity_for_panel = linked_entity
                    logger.debug(f"Resolved Task to linked entity for panel: {target_entity_for_panel}")
                else:
                    logger.warning(f"Task selected, but couldn't resolve linked entity from: {self._entity_data}")
            else:
                target_entity_for_panel = self._entity_data  # Asset, Shot, etc.
                logger.debug(f"Using selected entity for panel: {target_entity_for_panel}")
        else:
            # This case should ideally not happen due to the early exit, but good to keep
            logger.warning("self._entity_data is unexpectedly None after extraction.")

        # 4. Get the Filesystem Path (using the primary clicked entity data)
        # _get_entity_info handles Task resolution internally if needed for path
        self._entity_path, _, _ = self._get_entity_info(self._entity_data)
        logger.debug(f"Entity path determined as: {self._entity_path}")

        # 5. Trigger Publish Model Load (using the selected tree item)
        # We call this primarily for its side effect of loading the publish model.
        # We no longer rely on its return value here.
        self._load_publishes_for_entity_item(selected_item)
        # Note: _load_publishes_for_entity_item internally calls _publish_model.load_data,
        # which *should* use the item's sg_data to set its filters correctly.

        # 6. Get Data from Models (after they've potentially been updated)
        self.get_current_sg_data()  # Populates self._sg_data from the publish model
        self._update_perforce_data()  # Populates self._fstat_dict using self._sg_data and self._entity_path

        # Optional: Debugging
        # self.print_publish_data()

        # 7. Update UI Elements (using timers for safety)

        # Update panel, passing the RESOLVED entity for navigation
        logger.debug(f"Scheduling panel update for: {target_entity_for_panel}")
        QtCore.QTimer.singleShot(0, lambda: self._get_shotgun_panel_widget(target_entity_for_panel))

        # Update other views based on the current mode and populated data
        if self.main_view_mode == self.MAIN_VIEW_COLUMN:
            logger.debug("Scheduling Column View update.")
            # _set_column_view_mode calls _populate_column_view_widget which uses self._sg_data and self._fstat_dict
            QtCore.QTimer.singleShot(0, self._set_column_view_mode)
        if self.main_view_mode == self.MAIN_VIEW_SUBMITTED:
            logger.debug("Scheduling Submitted View update.")
            # _populate_submitted_widget uses self._fstat_dict
            QtCore.QTimer.singleShot(0, self._populate_submitted_widget)
        # Add similar blocks for MAIN_VIEW_LIST, MAIN_VIEW_THUMB if they need explicit updates
        # based on self._sg_data / self._fstat_dict after selection change.
        # Currently, they might update automatically via model/view connections.

        # Update breadcrumbs and history (already done in _reload_treeview, but let's ensure it's consistent)
        # These were moved out of _reload_treeview in this refactor, place them here:
        self._populate_entity_breadcrumbs(selected_item)
        self._add_file_history_record(self._current_entity_preset, selected_item)
        self._setup_file_details_panel([])  # Clear details initially

        logger.debug("Finished _on_treeview_item_selected.")


# --- IMPORTANT: Modify _reload_treeview ---
# Remove the responsibility of returning sg_data from _reload_treeview
def _reload_treeview(self):
    """
    Handles UI updates related to tree view selection *before*
    the main data loading in _on_treeview_item_selected.
    Returns the selected QStandardItem.
    """
    selected_item = self._get_selected_entity()

    # Update breadcrumbs (Moved to _on_treeview_item_selected)
    # self._populate_entity_breadcrumbs(selected_item)

    # Fetch more items in the tree if needed
    if selected_item:
        model = self._entity_presets[self._current_entity_preset].model
        if model.canFetchMore(selected_item.index()):
            model.fetchMore(selected_item.index())

    # Add to history (Moved to _on_treeview_item_selected)
    # self._add_file_history_record(self._current_entity_preset, selected_item)

    # Clear details panel (Moved to _on_treeview_item_selected)
    # self._setup_file_details_panel([])

    # Trigger publish model load (Moved to _on_treeview_item_selected)
    # self._load_publishes_for_entity_item(selected_item)

    # Return ONLY the selected item
    return selected_item  # <-- Changed return value