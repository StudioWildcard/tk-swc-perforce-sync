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
try:
    import queue
except ImportError:
    import Queue as queue

import sgtk

from sgtk.platform.qt import QtCore
for name, cls in QtCore.__dict__.items():
    if isinstance(cls, type): globals()[name] = cls

from P4 import Progress as P4Progress

from .utils import local_to_depot

logger = sgtk.platform.get_logger(__name__)

MAX_SYNC_THREADS = 16


class CancelProgress(P4Progress):
    """Minimal P4.Progress handler that cancels run_sync mid-transfer.

    P4Python calls update() periodically on the SAME thread that called
    run_sync, so checking a flag here is thread-safe. Returning non-zero
    from update() tells P4 to abort the current operation.
    """

    def __init__(self, cancel_flag_fn):
        P4Progress.__init__(self)
        self._cancel_flag_fn = cancel_flag_fn

    def init(self, type):
        pass

    def setDescription(self, description, unit):
        pass

    def setTotal(self, total):
        pass

    def update(self, position):
        return 1 if self._cancel_flag_fn() else 0

    def done(self, fail):
        pass


class PerforceSyncManager(QtCore.QObject):
    """
    Manages all Perforce connection and sync operations.

    Signals:
        sync_completed: Emitted when a sync operation finishes.
        log_message(str, int): Log message with flag level.
        progress_update(float): Progress bar value (0-100).
        sync_info(int, str): Emitted with (file_count, formatted_size) before sync.
        clobber_prompt(list): Emitted with list of depot paths that couldn't overwrite
            writable local files. Connect to prompt the user for force-sync.
    """

    sync_completed = QtCore.Signal()
    log_message = QtCore.Signal(str, int)
    progress_update = QtCore.Signal(float)
    sync_info = QtCore.Signal(int, str)
    clobber_prompt = QtCore.Signal(list)

    def __init__(self, app, p4_framework, parent=None):
        super(PerforceSyncManager, self).__init__(parent)
        self._app = app
        self._fw = p4_framework
        self._p4 = self._fw.connection.connect()
        self._root_path = self._app.sgtk.roots.get('primary')
        self._drive = self._root_path[0:2] if self._root_path else ""
        self._sync_active = threading.Event()
        self._cancel_requested = False
        self._sync_thread = None
        self._worker_connections = []  # P4 connections for active worker threads
        self._worker_connections_lock = threading.Lock()

        # Clobber prompt coordination between coordinator thread and UI
        self._clobber_response = threading.Event()
        self._clobber_force = False  # True = overwrite, False = skip

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

    def create_thread_connection(self):
        """
        Create a new P4 connection for use in a worker thread.

        Per Perforce P4Python docs, each thread must use its own connection.
        The returned connection should be disconnected when the thread is done.

        :returns: A new P4 connection object.
        """
        return self._fw.connection.connect()

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
        Syncs all files within the given entity path that need updating.
        Runs dry-run + parallel sync entirely in a background thread.
        """
        logger.info("Starting sync for the current selection...")
        logger.info("Selected Entity path {}".format(entity_path))

        if not entity_path:
            logger.warning("No valid path found for the selected entity.")
            self.log_message.emit(
                "\n <span style='color:#FFD700'>No valid path found for the selected entity.</span> \n", 2)
            return

        depot_path_base = self.convert_local_to_depot(entity_path)
        if not depot_path_base:
            logger.error("Could not convert local path '{}' to a Perforce depot path.".format(entity_path))
            self.log_message.emit(
                "\n <span style='color:#CC3333'>Error: Could not map '{}' to a Perforce path.</span> \n".format(entity_path), 2)
            return

        wildcard = depot_path_base.rstrip('/') + '/...'
        self._start_sync_thread(depot_wildcard=wildcard)

    def sync_files_list(self, files_to_sync):
        """
        Sync a list of local file paths using parallel sync.
        Returns immediately — listen for sync_completed signal.
        """
        if not files_to_sync:
            self.log_message.emit("\n <span style='color:#2C93E2'>No files to sync.</span> \n", 2)
            return

        depot_files = [self.convert_local_to_depot(f) for f in files_to_sync]
        depot_files = [f for f in depot_files if f]
        if not depot_files:
            self.log_message.emit("\n <span style='color:#2C93E2'>No files to sync.</span> \n", 2)
            return

        self.sync_info.emit(len(depot_files), "")
        self._start_sync_thread(depot_files=depot_files)

    def cancel_sync(self):
        """Cancel the current sync operation.

        Sets the cancel flag which is checked in two places:
        1. Each worker's while-loop condition (between files)
        2. CancelProgress.update() callback (during file transfers)

        The CancelProgress handler is called by P4 on the worker's own
        thread during transfers, so returning 1 safely aborts run_sync
        mid-transfer — even for large files. No cross-thread P4 access.

        The coordinator's finally block handles connection cleanup and
        emits sync_completed once all workers have stopped.
        """
        self._cancel_requested = True
        self.log_message.emit(
            "\n <span style='color:#FFD700'>Cancelling sync...</span> \n", 2)

        # Unblock coordinator if it's waiting for clobber response.
        self._clobber_response.set()

    def respond_to_clobber(self, overwrite):
        """Called by the UI after the user responds to the clobber prompt.

        :param overwrite: True to force-sync writable files, False to skip them.
        """
        self._clobber_force = overwrite
        self._clobber_response.set()

    def _start_sync_thread(self, depot_files=None, depot_wildcard=None):
        """Start a multi-threaded sync with file-count progress.

        Provide either depot_files (list of specific depot paths) or
        depot_wildcard (e.g. //depot/project/... for dry-run + sync).

        Before syncing, checks for writable local files that would cause
        "can't clobber" errors.  If any are found, emits clobber_prompt
        and blocks until the user responds (via respond_to_clobber).

        Spawns up to MAX_SYNC_THREADS worker threads, each with its own
        P4 connection, pulling files from a shared queue. Progress is
        reported per completed file. Cancel disconnects all workers.
        """
        # If a previous sync thread is still running, wait briefly.
        if self._sync_thread and self._sync_thread.is_alive():
            logger.warning("Previous sync thread still running — waiting up to 5s...")
            self._sync_thread.join(timeout=5)
            if self._sync_thread.is_alive():
                logger.warning("Previous sync thread did not stop — starting new sync anyway.")

        self._cancel_requested = False
        self._clobber_response.clear()
        self._clobber_force = False
        self._sync_active.set()

        def coordinator():
            coord_p4 = None
            try:
                coord_p4 = self.create_thread_connection()

                # --- Discover files to sync ---
                if depot_wildcard:
                    logger.info("Running dry-run sync on: {}".format(depot_wildcard))
                    self.sync_info.emit(0, "Checking...")
                    sync_preview = coord_p4.run_sync("-n", depot_wildcard)

                    file_entries = []
                    if isinstance(sync_preview, list):
                        file_entries = [e for e in sync_preview
                                        if isinstance(e, dict) and "depotFile" in e]

                    if not file_entries:
                        self.log_message.emit(
                            "\n <span style='color:#2C93E2'>All files are up to date.</span> \n", 2)
                        return

                    files = [e["depotFile"] for e in file_entries]

                    # Extract total size
                    last = sync_preview[-1] if sync_preview else {}
                    total_size = int(last.get("totalFileSize", 0)) if isinstance(last, dict) else 0
                    if total_size == 0:
                        for entry in file_entries:
                            if "fileSize" in entry:
                                total_size += int(entry["fileSize"])
                    size_str = self._format_size(total_size)
                    self.sync_info.emit(len(files), size_str)
                    logger.info("Dry-run found {} files ({})".format(len(files), size_str))

                    # Build depot->local path map from dry-run results
                    depot_to_local = {}
                    for entry in file_entries:
                        client_file = entry.get("clientFile")
                        if client_file:
                            depot_to_local[entry["depotFile"]] = client_file
                else:
                    files = depot_files
                    total_size = 0
                    depot_to_local = {}
                    # For pre-selected files, build the path map
                    for depot_file in files:
                        local = self.get_client_file(depot_file)
                        if local:
                            depot_to_local[depot_file] = local

                if self._cancel_requested:
                    return

                # --- Pre-check for writable files that would cause clobber ---
                writable_files = []
                for depot_file in files:
                    local_path = depot_to_local.get(depot_file)
                    if local_path and os.path.isfile(local_path):
                        try:
                            if os.access(local_path, os.W_OK):
                                writable_files.append(depot_file)
                        except OSError:
                            pass

                force_files = set()  # depot paths to sync with -f
                if writable_files:
                    logger.info("Found {} writable file(s) that would be clobbered".format(
                        len(writable_files)))
                    self.log_message.emit(
                        "\n <span style='color:#FFD700'>Found {} writable file(s) — "
                        "waiting for user response...</span> \n".format(len(writable_files)), 2)

                    # Emit prompt and block until user responds
                    self._clobber_response.clear()
                    self.clobber_prompt.emit(list(writable_files))
                    self._clobber_response.wait()

                    if self._cancel_requested:
                        return

                    if self._clobber_force:
                        force_files = set(writable_files)
                        logger.info("User chose to overwrite %d writable file(s)", len(force_files))
                    else:
                        # Skip writable files
                        skip_set = set(writable_files)
                        files = [f for f in files if f not in skip_set]
                        logger.info("User chose to skip %d writable file(s), %d files remain",
                                    len(skip_set), len(files))
                        if not files:
                            self.log_message.emit(
                                "\n <span style='color:#2C93E2'>All remaining files skipped.</span> \n", 2)
                            return

                total = len(files)
                completed = [0]
                completed_lock = threading.Lock()
                errors = []

                # --- Build file queue ---
                file_queue = queue.Queue()
                for f in files:
                    file_queue.put(f)

                # --- Worker function ---
                def worker(worker_p4):
                    while not self._cancel_requested:
                        try:
                            depot_file = file_queue.get_nowait()
                        except queue.Empty:
                            break
                        file_name = depot_file.rsplit("/", 1)[-1]
                        try:
                            logger.debug("Worker syncing: %s", depot_file)
                            if depot_file in force_files:
                                worker_p4.run_sync("-f", "{}#head".format(depot_file))
                            else:
                                worker_p4.run_sync("{}#head".format(depot_file))
                        except Exception as e:
                            if self._cancel_requested:
                                break
                            logger.error("Failed to sync %s: %s", depot_file, e)
                            errors.append((depot_file, str(e)))
                        with completed_lock:
                            completed[0] += 1
                            count = completed[0]
                            pct = (count / total) * 100.0
                        self.log_message.emit("({}/{}) {}".format(count, total, file_name), 3)
                        self.progress_update.emit(pct)

                # --- Create connections and spawn workers ---
                num_workers = min(MAX_SYNC_THREADS, total)
                self.log_message.emit(
                    "\n <span style='color:#2C93E2'>Starting sync of {} files "
                    "({} threads)...</span> \n".format(total, num_workers), 2)
                logger.info("Spawning %d sync workers for %d files", num_workers, total)

                worker_connections = []
                try:
                    # Create all connections sequentially.
                    # Reuse coord_p4 as the first worker connection.
                    worker_connections.append(coord_p4)
                    for i in range(1, num_workers):
                        if self._cancel_requested:
                            break
                        wp4 = self.create_thread_connection()
                        worker_connections.append(wp4)

                    # Attach cancel-aware progress handler to each connection.
                    # P4 calls progress.update() on the worker's own thread
                    # during file transfers, so returning 1 safely aborts
                    # run_sync mid-transfer without cross-thread issues.
                    for wp4 in worker_connections:
                        wp4.progress = CancelProgress(
                            lambda: self._cancel_requested
                        )

                    # Track connections for cleanup
                    with self._worker_connections_lock:
                        self._worker_connections = list(worker_connections)

                    # Spawn worker threads
                    workers = []
                    for wp4 in worker_connections:
                        if self._cancel_requested:
                            break
                        w = threading.Thread(target=worker, args=(wp4,), daemon=True)
                        workers.append(w)
                        w.start()

                    # Wait for all workers to finish
                    for w in workers:
                        w.join()

                finally:
                    with self._worker_connections_lock:
                        self._worker_connections = []
                    for wp4 in worker_connections[1:]:
                        try:
                            wp4.disconnect()
                        except Exception:
                            pass

                # --- Report results ---
                if self._cancel_requested:
                    self.log_message.emit(
                        "\n <span style='color:#FFD700'>Sync cancelled ({}/{} files synced).</span> \n".format(
                            completed[0], total), 2)
                elif errors:
                    self.log_message.emit(
                        "\n <span style='color:#FFD700'>Sync complete with {} error(s) ({}/{} files).</span> \n".format(
                            len(errors), completed[0], total), 2)
                else:
                    self.log_message.emit(
                        "\n <span style='color:#2C93E2'>Sync complete ({} files).</span> \n".format(
                            completed[0]), 2)

            except Exception as e:
                if self._cancel_requested:
                    self.log_message.emit(
                        "\n <span style='color:#FFD700'>Sync cancelled.</span> \n", 2)
                else:
                    logger.error("Sync failed: {}".format(e))
                    self.log_message.emit(
                        "\n <span style='color:#CC3333'>Sync failed: {}</span> \n".format(e), 2)
            finally:
                if coord_p4:
                    try:
                        coord_p4.disconnect()
                    except Exception:
                        pass
                was_active = self._sync_active.is_set()
                self._sync_active.clear()
                self._cancel_requested = False
                if was_active:
                    self.sync_completed.emit()

        self._sync_thread = threading.Thread(target=coordinator, daemon=True)
        self._sync_thread.start()

    @staticmethod
    def _format_size(size_bytes):
        """Format bytes into a human-readable string."""
        if size_bytes >= 1024 ** 3:
            return "{:.1f} GB".format(size_bytes / (1024 ** 3))
        elif size_bytes >= 1024 ** 2:
            return "{:.1f} MB".format(size_bytes / (1024 ** 2))
        elif size_bytes >= 1024:
            return "{:.1f} KB".format(size_bytes / 1024)
        return "{} B".format(size_bytes)

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
        logger.debug("Parent files to sync: {}".format(files_to_sync))

        if not files_to_sync:
            self.log_message.emit(
                "\n <span style='color:#2C93E2'>No file sync required for entity parents.</span> \n", 2)
        else:
            self.log_message.emit(
                "\n <span style='color:#2C93E2'>Syncing {} published files of entity parents...</span> \n".format(
                    len(files_to_sync)), 2)
            self.sync_files_list(files_to_sync)

    def sync_entity_children_published_files(self, entity_children, app):
        """Sync published files for child entities."""
        files_to_sync = self.prepare_entity_children_published_files(entity_children, app)

        if not files_to_sync:
            self.log_message.emit(
                "\n <span style='color:#2C93E2'>No file sync required for entity children.</span> \n", 2)
        else:
            self.log_message.emit(
                "\n <span style='color:#2C93E2'>Syncing {} published files of entity children...</span> \n".format(
                    len(files_to_sync)), 2)
            self.sync_files_list(files_to_sync)

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
