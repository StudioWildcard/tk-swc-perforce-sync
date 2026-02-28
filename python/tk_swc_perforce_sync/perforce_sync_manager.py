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
PerforceSyncManager - Owns the Perforce connection and all sync/fstat/changelist-query
operations. Single source of truth for the P4 connection object.
"""

import os
import time
import threading
import logging

import sgtk

from sgtk.platform.qt import QtCore
for name, cls in QtCore.__dict__.items():
    if isinstance(cls, type): globals()[name] = cls

from .utils import local_to_depot

logger = sgtk.platform.get_logger(__name__)


class PerforceSyncManager(QtCore.QObject):
    """
    Manages all Perforce connection and sync operations.

    Signals:
        sync_completed: Emitted when a sync operation finishes.
        log_message(str, int): Log message with flag level.
        progress_update(float): Progress bar value (0-100).
    """

    sync_completed = QtCore.Signal()
    log_message = QtCore.Signal(str, int)
    progress_update = QtCore.Signal(float)

    def __init__(self, app, p4_framework, parent=None):
        super(PerforceSyncManager, self).__init__(parent)
        self._app = app
        self._fw = p4_framework
        self._p4 = self._fw.connection.connect()
        self._root_path = self._app.sgtk.roots.get('primary')
        self._drive = self._root_path[0:2] if self._root_path else ""
        self._sync_active = False
        self.sync_command = []

        # Sync count cache
        self._sync_count_cache = {}
        self._sync_count_cache_timeout = 60  # seconds
        self._sync_count_cache_lock = threading.Lock()

    # -------------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------------

    @property
    def p4(self):
        """The Perforce connection object."""
        return self._p4

    @property
    def drive(self):
        """The drive letter for depot-to-local conversion (e.g. 'B:')."""
        return self._drive

    # -------------------------------------------------------------------------
    # P4 Connection
    # -------------------------------------------------------------------------

    def reconnect(self):
        """
        Reconnect to Perforce. If a connection can't be established with
        the current settings then the connection UI will be shown.
        """
        try:
            if not self._p4:
                logger.debug("Connecting to perforce ...")
                self._fw = sgtk.platform.get_framework("tk-framework-perforce")
                self._p4 = self._fw.connection.connect()
        except:
            logger.debug("Failed to connect!")
            raise

    # -------------------------------------------------------------------------
    # P4 Query Wrappers (with retry logic)
    # -------------------------------------------------------------------------

    def get_client_name(self):
        max_retries = 5
        client = None
        try:
            for attempt in range(max_retries):
                client = self._p4.fetch_client()
                if not client:
                    time.sleep(0.3)
                    continue
                else:
                    break
        except:
            pass
        return client

    def get_change_lists(self, workspace):
        max_retries = 5
        change_lists = None
        try:
            for attempt in range(max_retries):
                change_lists = self._p4.run_changes("-l", "-s", "pending", "-c", workspace)
                if not change_lists:
                    time.sleep(0.3)
                    continue
                else:
                    break
        except:
            pass
        return change_lists

    def get_desc_files(self, key):
        max_retries = 3
        desc_files = None
        try:
            for attempt in range(max_retries):
                desc_files = self._p4.run("describe", "-O", key)
                if not desc_files:
                    time.sleep(0.3)
                    continue
                else:
                    break
        except:
            pass
        return desc_files

    def get_fstat_list(self, depot_file):
        max_retries = 3
        fstat_list = None
        try:
            for attempt in range(max_retries):
                fstat_list = self._p4.run("fstat", depot_file)
                if not fstat_list:
                    time.sleep(0.3)
                    continue
                else:
                    break
        except:
            pass
        return fstat_list

    def get_client_file(self, depot_file):
        """
        Convert depot path to local path.
        E.g. '//Ark2Depot/Content/...' -> 'B:\\Ark2Depot\\Content\\...'
        """
        client_file = None
        try:
            if depot_file:
                client_file = "{}{}".format(self._drive, depot_file)
        except:
            pass
        return client_file

    # -------------------------------------------------------------------------
    # Path Conversion Helpers
    # -------------------------------------------------------------------------

    def convert_local_to_depot(self, local_path):
        """Convert a local file path to a Perforce depot path."""
        return local_to_depot(local_path)

    @staticmethod
    def create_key(file_path):
        """Normalize a file path for use as a dictionary key."""
        return file_path.replace("\\", "").replace("/", "").lower() if file_path else None

    @staticmethod
    def to_sync(have_rev, head_rev):
        """Determine if a file should be synced based on revision numbers."""
        have_rev_int = int(have_rev)
        head_rev_int = int(head_rev)
        if head_rev_int > 0 and have_rev_int < head_rev_int:
            return True
        return False

    # -------------------------------------------------------------------------
    # Sync Operations
    # -------------------------------------------------------------------------

    def sync_current_entity(self, entity_path):
        """
        Finds the depot path for the given entity path and syncs all files
        within it that need updating. Runs sync in a background thread.
        """
        logger.info("Starting sync for the current selection...")
        logger.info(f"Selected Entity path {entity_path}")

        if not entity_path:
            logger.warning("No valid path found for the selected entity.")
            self.log_message.emit(
                "\n <span style='color:#FFD700'>No valid path found for the selected entity.</span> \n", 2)
            return

        # Convert local path to Perforce depot path
        depot_path_base = self.convert_local_to_depot(entity_path)
        if not depot_path_base:
            logger.error(f"Could not convert local path '{entity_path}' to a Perforce depot path.")
            self.log_message.emit(
                f"\n <span style='color:#CC3333'>Error: Could not map '{entity_path}' to a Perforce path.</span> \n", 2)
            return

        # Build Perforce wildcard path
        depot_path_wildcard = depot_path_base.rstrip('/') + '/...'
        logger.info(f"[SYNC CHECK] Running dry-run sync on: {depot_path_wildcard}")

        # Run dry-run sync to list files
        try:
            if not self._p4.connected():
                self._p4.connect()
            sync_output = self._p4.run_sync("-n", depot_path_wildcard)
            if not isinstance(sync_output, list):
                logger.error(
                    f"[SYNC CHECK] Expected list of files, got {type(sync_output)} for path {depot_path_wildcard}")
                self.log_message.emit(
                    f"\n <span style='color:#CC3333'>Dry-run sync failed: Invalid response for {depot_path_wildcard}</span> \n",
                    2)
                return
            depot_files = [entry.get("depotFile") for entry in sync_output if "depotFile" in entry]
            num_files = len(depot_files)
        except Exception as e:
            return

        logger.info(f"Total files to sync: {num_files}")
        self.log_message.emit(f"\n <span style='color:#2C93E2'>Found {num_files} files that need syncing.</span> \n", 2)

        if depot_files:
            logger.info("Files to sync:")
            for i, path in enumerate(depot_files, 1):
                msg = f"[{i:02}] {path}"
                self.log_message.emit(msg, 3)
        else:
            logger.info("No individual depot files found in sync output.")
            self.log_message.emit("\n <span style='color:#2C93E2'>No files to sync.</span> \n", 2)
            self.progress_update.emit(100)
            self.sync_completed.emit()
            return

        # Define sync logic in thread
        def sync_thread_fn():
            try:
                for i, depot_file in enumerate(depot_files, 1):
                    if not hasattr(self, '_sync_active') or not self._sync_active:
                        logger.info("Sync operation cancelled due to new sync request.")
                        return

                    self._p4.run_sync(depot_file)
                    progress = (i / num_files) * 100
                    file_name = depot_file.split('/')[-1]
                    msg = f"Syncing {file_name} ({i}/{num_files})" if logger.isEnabledFor(
                        logging.DEBUG) else f"({i}/{num_files}) Syncing..."
                    self.log_message.emit(msg, 3)
                    self.progress_update.emit(progress)
            except Exception as e:
                logger.error(f"Sync failed: {e}")
                self.log_message.emit(
                    f"\n <span style='color:#CC3333'>Sync failed: {e}</span> \n", 2)
            finally:
                self._sync_active = False
                self.log_message.emit("\n <span style='color:#2C93E2'>Sync complete for current selection.</span> \n", 2)
                self.sync_completed.emit()

        # Set sync active flag and start thread
        self._sync_active = True
        sync_thread = threading.Thread(target=sync_thread_fn)
        sync_thread.start()

    def sync_files_list(self, files_to_sync):
        """
        Sync a list of local file paths using the primary threading method.
        Returns after sync is complete.
        """
        files_to_sync_count = len(files_to_sync)
        if files_to_sync_count == 0:
            self.log_message.emit("\n <span style='color:#2C93E2'>No Need to sync</span> \n", 2)
            return

        self.log_message.emit(
            "\n <span style='color:#2C93E2'>Syncing {} files ... </span> \n".format(files_to_sync_count), 2)
        self._do_sync_files_threading_thread_2(files_to_sync)
        self.log_message.emit("\n <span style='color:#2C93E2'>Syncing files is complete</span> \n", 2)

    def _do_sync_files_threading_thread_2(self, files_to_sync, entity=None):
        """Primary sync method using P4 parallel sync with progress tracking."""
        self.sync_command = []
        self.sync_command.append("sync")
        self.sync_command.append("-f")
        self.sync_command.append("--parallel")
        self.sync_command.append("threads=16,batch=4,batchsize=4096,min=1,minsize=1")

        for i, file_path in enumerate(files_to_sync):
            depot_path = self.convert_local_to_depot(file_path)
            depot_path = "{}#head".format(depot_path)
            self.sync_command.append(depot_path)

        sync_thread = threading.Thread(target=self._run_sync, args=())
        sync_thread.start()

        total = len(files_to_sync)
        for i, file_path in enumerate(files_to_sync):
            msg = "({}/{})  Syncing file: {}".format(i + 1, total, file_path)
            self.log_message.emit(msg, 3)
            progress_sum = ((i + 1) / total) * 100
            self.progress_update.emit(progress_sum)
            QCoreApplication.processEvents()
            time.sleep(0.15)

        self.log_message.emit(
            "\n <span style='color:#2C93E2'>Finalizing file syncing, please wait...</span> \n", 2)

        while sync_thread.is_alive():
            QCoreApplication.processEvents()

    def _run_sync(self):
        """Thread target: execute the P4 sync command."""
        p4_response = self._p4.run(self.sync_command)
        logger.debug("Result of syncing files ...")
        for entry in p4_response:
            logger.debug("{}".format(entry))

        if any(entry.get('error') for entry in p4_response):
            error_messages = [entry['error'] for entry in p4_response if entry.get('error')]
            logger.error("File sync failed with errors: {}".format(", ".join(error_messages)))

        logger.debug("File sync completed.")

    def get_latest_revision(self, files_to_sync):
        """Force-sync a list of files to head revision."""
        for file_path in files_to_sync:
            p4_result = self._p4.run("sync", "-f", file_path + "#head")
            logger.debug("Syncing file: {}".format(file_path))

    def get_files_to_sync(self, publish_view_model, shotgun_model_module, SgLatestPublishModel):
        """
        Iterate over the publish view model to find files that need syncing.

        Args:
            publish_view_model: The model behind the publish view.
            shotgun_model_module: The shotgun_model module for get_sg_data.
            SgLatestPublishModel: The model class for IS_FOLDER_ROLE constant.

        Returns:
            tuple: (files_to_sync list, total_file_count)
        """
        total_file_count = 0
        files_to_sync = []

        for row in range(publish_view_model.rowCount()):
            model_index = publish_view_model.index(row, 0)
            proxy_model = model_index.model()
            source_index = proxy_model.mapToSource(model_index)
            item = source_index.model().itemFromIndex(source_index)

            is_folder = item.data(SgLatestPublishModel.IS_FOLDER_ROLE)
            if not is_folder:
                total_file_count += 1
                sg_item = shotgun_model_module.get_sg_data(model_index)
                sg_item_path = sg_item.get("path", None)
                if sg_item_path:
                    local_path = sg_item_path.get("local_path", None)
                    if local_path:
                        have_rev = sg_item.get('haveRev', "0")
                        head_rev = sg_item.get('headRev', "0")
                        if self.to_sync(have_rev, head_rev):
                            files_to_sync.append(local_path)

        return files_to_sync, total_file_count

    def get_perforce_summary(self, publish_view_model, shotgun_model_module, SgLatestPublishModel):
        """Log a summary of files that need syncing."""
        files_to_sync, total_file_count = self.get_files_to_sync(
            publish_view_model, shotgun_model_module, SgLatestPublishModel)
        files_to_sync_count = len(files_to_sync)
        if files_to_sync_count == 0:
            self.log_message.emit("\n <span style='color:#2C93E2'>No Need to sync</span> \n", 2)

    # -------------------------------------------------------------------------
    # Entity Parent/Children Sync
    # -------------------------------------------------------------------------

    def get_entity_parents(self, entity_data, app):
        """
        Get the entity parents for a given item from ShotGrid.

        Args:
            entity_data: ShotGrid entity data dict.
            app: The sgtk app bundle for SG queries.

        Returns:
            list: Parent entity dicts with 'entity_path' populated.
        """
        entity_parents = []
        if entity_data:
            entity_id = entity_data.get("id", None)
            entity_type = entity_data.get("type", None)
            if "entity" in entity_data:
                entity_info = entity_data.get("entity", None)
                if entity_info:
                    entity_id = entity_info.get("id", None)
                    entity_type = entity_info.get("type", None)

            if entity_id and entity_type:
                filters = [["id", "is", entity_id]]
                fields = ["id", "code", "type", "parents", "sg_asset_parent", "project", "sg_status_list"]
                published_entities = app.shotgun.find(entity_type, filters, fields)

                for published_entity in published_entities:
                    asset_parent = published_entity.get("sg_asset_parent", None)
                    if asset_parent:
                        entity_parents.append(asset_parent)
                    linked_assets = published_entity.get("parents", None)
                    if linked_assets:
                        for parent in linked_assets:
                            entity_parents.append(parent)

        return entity_parents

    def prepare_entity_parents_published_files(self, entity_parents, app):
        """
        Get published files for parent entities and determine which need syncing.

        Args:
            entity_parents: List of parent entity dicts.
            app: The sgtk app bundle for SG queries.

        Returns:
            list: Local file paths that need syncing.
        """
        entity_parents_published_files_list = []
        for parent in entity_parents:
            if parent:
                parent_type = parent.get("type", None)
                parent_id = parent.get("id", None)
                if parent_id and parent_type:
                    filters = [["entity", "is", {"type": parent_type, "id": parent_id}]]
                    fields = ["id", "code", "type", "entity", "project", "name", "path", "path",
                              "publish_type_field", 'published_file_type', 'created_by', 'created_at']
                    published_files = app.shotgun.find("PublishedFile", filters, fields)
                    entity_parents_published_files_list.extend(published_files)

        files_to_sync = []
        self.log_message.emit("\n <span style='color:#2C93E2'>Preparing entity parents files...</span> \n", 2)
        for published_file in entity_parents_published_files_list:
            if 'path' in published_file:
                local_path = published_file['path'].get('local_path', None)
                if local_path in files_to_sync:
                    continue
                if local_path:
                    head_rev = published_file.get('headRev', None)
                    have_rev = published_file.get('haveRev', None)
                    try:
                        code = published_file.get('code', None)
                        if code:
                            code = code.split("#")[-1]
                        msg = "Checking file {}#{}".format(local_path, code)
                        self.log_message.emit(msg, 4)
                    except:
                        pass

                    if not head_rev and not have_rev:
                        fstat_list = self._p4.run_fstat(local_path)
                        if isinstance(fstat_list, list) and fstat_list:
                            for file_info in fstat_list:
                                if not isinstance(file_info, dict):
                                    continue
                                if file_info:
                                    if isinstance(file_info, list) and len(file_info) == 1:
                                        file_info = file_info[0]
                                    head_rev = file_info.get('headRev', None)
                                    have_rev = file_info.get('haveRev', None)
                                    published_file["headRev"] = head_rev
                                    published_file["haveRev"] = have_rev
                    if head_rev:
                        if not have_rev:
                            have_rev = "0"
                        if self.to_sync(have_rev, head_rev):
                            if local_path not in files_to_sync:
                                files_to_sync.append(local_path)

        return files_to_sync

    def prepare_entity_children_published_files(self, entity_children, app):
        """
        Get published files for child entities and determine which need syncing.

        Args:
            entity_children: List of child entity dicts.
            app: The sgtk app bundle for SG queries.

        Returns:
            list: Local file paths that need syncing.
        """
        entity_children_published_files_list = []
        for child in entity_children:
            if child:
                child_type = child.get("type", None)
                child_id = child.get("id", None)
                if child_id and child_type:
                    filters = [["entity", "is", {"type": child_type, "id": child_id}]]
                    fields = ["id", "code", "type", "entity", "parents", "sg_asset_parent", "sg_assets", "project", "name", "image",
                              "path", "task", "publish_type_field", 'published_file_type', 'created_by', 'created_at',
                              "sg_asset_library", "asset_section", "asset_category", "sg_asset_type", "sg_status_list"]
                    published_files = app.shotgun.find("PublishedFile", filters, fields)
                    entity_children_published_files_list.extend(published_files)

        files_to_sync = []
        self.log_message.emit("\n <span style='color:#2C93E2'>Preparing entity children files...</span> \n", 2)
        for published_file in entity_children_published_files_list:
            if 'path' in published_file:
                local_path = published_file['path'].get('local_path', None)
                if local_path:
                    msg = "Checking file {}".format(local_path)
                    self.log_message.emit(msg, 4)
                    head_rev = published_file.get('headRev', None)
                    have_rev = published_file.get('haveRev', None)
                    if not head_rev and not have_rev:
                        fstat_list = self._p4.run_fstat(local_path)
                        if isinstance(fstat_list, list) and fstat_list:
                            for file_info in fstat_list:
                                if not isinstance(file_info, dict):
                                    continue
                                if file_info:
                                    if isinstance(file_info, list) and len(file_info) == 1:
                                        file_info = file_info[0]
                                    head_rev = file_info.get('headRev', None)
                                    have_rev = file_info.get('haveRev', None)
                                    published_file["headRev"] = head_rev
                                    published_file["haveRev"] = have_rev
                    if head_rev:
                        if not have_rev:
                            have_rev = "0"
                        if self.to_sync(have_rev, head_rev):
                            files_to_sync.append(local_path)

        return files_to_sync

    def sync_entity_parents_published_files(self, entity_parents, app):
        """Sync published files for parent entities."""
        files_to_sync = self.prepare_entity_parents_published_files(entity_parents, app)
        logger.debug(">>>>>>>>>>> Parent files to sync:{}".format(files_to_sync))

        files_to_sync_count = len(files_to_sync)
        if files_to_sync_count == 0:
            self.log_message.emit(
                "\n <span style='color:#2C93E2'>No file sync required for entity parents.</span> \n", 2)
        elif files_to_sync_count > 0:
            self.log_message.emit(
                "\n <span style='color:#2C93E2'>Syncing {} published files of entity parents.... </span> \n".format(
                    files_to_sync_count), 2)
            self._do_sync_files_threading_thread_2(files_to_sync, entity=True)
            self.log_message.emit(
                "\n <span style='color:#2C93E2'>Syncing entity parents published files is complete</span> \n", 2)

    def sync_entity_children_published_files(self, entity_children, app):
        """Sync published files for child entities."""
        files_to_sync = self.prepare_entity_children_published_files(entity_children, app)

        files_to_sync_count = len(files_to_sync)
        if files_to_sync_count == 0:
            self.log_message.emit(
                "\n <span style='color:#2C93E2'>No file sync required for entity children.</span> \n", 2)
        elif files_to_sync_count > 0:
            self.log_message.emit(
                "\n <span style='color:#2C93E2'>Syncing {} published files of entity children.... </span> \n".format(
                    files_to_sync_count), 2)
            self._do_sync_files_threading_thread_2(files_to_sync, entity=True)
            self.log_message.emit(
                "\n <span style='color:#2C93E2'>Syncing entity children published files is complete</span> \n", 2)

    def sync_entity_files(self, entity_parents, entity_children, app):
        """Sync both parent and child entity published files."""
        self.sync_entity_parents_published_files(entity_parents, app)
        self.sync_entity_children_published_files(entity_children, app)

    # -------------------------------------------------------------------------
    # Sync Count Cache
    # -------------------------------------------------------------------------

    def get_sync_count_for_entity(self, key):
        """
        Given a filesystem path, return how many files need to be synced.
        Checks both Perforce status and actual file existence on disk.
        """
        logger.debug(f"[SYNC CHECK] Checking entity: PATH={key}")

        try:
            sync_count = 0
            key = key.rstrip('/')

            fstat_list = self._p4.run_fstat(key + '/...')

            if not isinstance(fstat_list, list):
                logger.debug(f"[SYNC CHECK] run_fstat returned {type(fstat_list)} for {key}, skipping")
                return 0

            for i, fstat in enumerate(fstat_list):
                if not isinstance(fstat, dict):
                    continue
                if fstat:
                    client_file = fstat.get('clientFile')
                    have_rev = fstat.get('haveRev', "0")
                    head_rev = fstat.get('headRev', "0")

                    needs_sync = False

                    if have_rev == "0" or have_rev == "none":
                        needs_sync = True
                    elif client_file:
                        if not os.path.exists(client_file):
                            needs_sync = True
                        elif self.to_sync(have_rev, head_rev):
                            needs_sync = True

                    if needs_sync:
                        sync_count += 1

            logger.debug(f"[SYNC CHECK] Total files to sync: {sync_count}")
            return sync_count

        except Exception as e:
            logger.debug(f"[SYNC CHECK] Exception during sync check for entity path {key}: {e}")
            return 0

    def get_sync_count_for_entity_cached(self, key):
        """
        Cached version of get_sync_count_for_entity. Returns cached result
        if available and not expired, otherwise queries P4 and caches the result.
        """
        import time as _time
        now = _time.time()
        with self._sync_count_cache_lock:
            if key in self._sync_count_cache:
                cached_count, cached_time = self._sync_count_cache[key]
                if now - cached_time < self._sync_count_cache_timeout:
                    logger.debug(f"[SYNC CHECK] Using cached sync count for {key}: {cached_count}")
                    return cached_count

        # Cache miss or expired — do the real check
        count = self.get_sync_count_for_entity(key)

        with self._sync_count_cache_lock:
            self._sync_count_cache[key] = (count, now)

        return count

    def cleanup_sync_cache(self):
        """Remove expired entries from the sync count cache."""
        import time as _time
        now = _time.time()
        with self._sync_count_cache_lock:
            expired_keys = [
                k for k, (_, t) in self._sync_count_cache.items()
                if now - t >= self._sync_count_cache_timeout
            ]
            for k in expired_keys:
                del self._sync_count_cache[k]

    def invalidate_sync_cache(self, entity_path=None):
        """
        Invalidate sync count cache entries.
        If entity_path is given, only invalidate that entry and its parents.
        Otherwise, clear the entire cache.
        """
        with self._sync_count_cache_lock:
            if entity_path:
                keys_to_remove = [
                    k for k in self._sync_count_cache
                    if k.startswith(entity_path) or entity_path.startswith(k)
                ]
                for k in keys_to_remove:
                    del self._sync_count_cache[k]
            else:
                self._sync_count_cache.clear()
