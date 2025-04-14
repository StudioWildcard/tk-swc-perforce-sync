def refresh_entity_preset_tabs(self):
    """
    Refreshes the data displayed in the entity preset tabs, specifically
    updating the 'To Sync' count for the 'My Tasks' preset.
    """
    logger.debug("Refreshing entity preset tabs...")
    for preset_name, preset in self._entity_presets.items():
        if preset_name == "My Tasks":
            logger.debug("Refreshing 'My Tasks' preset tab.")
            view = preset.view
            proxy_model = preset.proxy_model
            source_model = proxy_model.sourceModel()

            # Ensure the model has the correct number of columns if it was somehow reset
            if source_model.columnCount() < 2:
                 source_model.setColumnCount(2)
                 source_model.setHorizontalHeaderLabels(["Name", "To Sync"])

            row_count = source_model.rowCount()
            logger.debug(f"Found {row_count} rows in 'My Tasks' model.")

            for row in range(row_count):
                proxy_index = proxy_model.index(row, 0)
                if not proxy_index.isValid():
                    # logger.debug(f"[REFRESH] Row {row}: Invalid proxy index")
                    continue

                source_index = proxy_model.mapToSource(proxy_index)
                if not source_index.isValid():
                    # logger.debug(f"[REFRESH] Row {row}: Invalid source index")
                    continue

                # Get item using source_index.model()
                item_model = source_index.model()
                item = item_model.itemFromIndex(source_index)

                if not item:
                    # logger.debug(f"[REFRESH] Row {row}: No item in model")
                    continue

                # Extract the Shotgun data and field value from the node item.
                (sg_data, entity_data) = model_item_data.get_item_data(item)

                entity_path, entity_id, entity_type = self._get_entity_info(entity_data)
                if not entity_id or not entity_type or not entity_path:
                    # logger.debug(
                    #    f"[REFRESH] Row {row}: Invalid entity info — Path: {entity_path}, ID: {entity_id}, Type: {entity_type}")
                    # Ensure the second column exists even if entity info is bad
                    if source_model.item(source_index.row(), 1) is None:
                         source_model.setItem(source_index.row(), 1, QStandardItem("N/A"))
                    continue

                # logger.debug(f"[REFRESH] Row {row}: Entity Path: {entity_path}")
                sync_count = self._get_sync_count_for_entity(entity_path)
                # logger.debug(f"[REFRESH] Row {row}: Sync count = {sync_count}")

                # Set value into the second column
                if sync_count == 0:
                    msg = "Up to date"
                else:
                    msg = "{} To Sync".format(sync_count)

                # Get or create the item for the second column
                desc_item = source_model.item(source_index.row(), 1)
                if desc_item is None:
                    desc_item = QStandardItem()
                    source_model.setItem(source_index.row(), 1, desc_item)

                desc_item.setText(str(msg)) # Update text
                sync_icon = self.sync_icons.get_sync_pixmap(sync_count)
                if sync_icon:
                    desc_item.setIcon(sync_icon) # Update icon
                else:
                    desc_item.setIcon(QIcon()) # Clear icon if none

            logger.debug("Finished refreshing 'My Tasks' preset tab.")
            # Trigger layout change to ensure the view updates visually
            source_model.layoutChanged.emit()
            view.update() # Force repaint if necessary
            break # Stop after refreshing 'My Tasks'

    logger.debug("Entity preset tabs refresh complete.")

def _refresh_all(self):
    mode = self.main_view_mode
    if mode == self.MAIN_VIEW_LIST:
        self.refresh_publish_data()
        #self._publish_model.async_refresh()
    elif mode == self.MAIN_VIEW_THUMB:
        self.refresh_publish_data()
        # self._publish_model.async_refresh()
    elif mode == self.MAIN_VIEW_COLUMN:
        self._populate_column_view_widget()
    elif mode == self.MAIN_VIEW_SUBMITTED:
        self._populate_submitted_widget()
    elif mode == self.MAIN_VIEW_PENDING:
        self._populate_pending_widget()

    # Refresh the entity preset tabs, specifically the 'My Tasks' sync count
    self.refresh_entity_preset_tabs()