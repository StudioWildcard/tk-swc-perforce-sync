
from .perforce_change import create_change, add_to_change, submit_change, add_to_default_changelist
import sgtk
logger = sgtk.platform.get_logger(__name__)

class PerformActions():
    def __init__(self, p4, sg_item, action, change, desc):
        self.p4 = p4
        self.sg_item = sg_item
        self.action = action
        self.change = change
        self.depot_file = sg_item.get("depotFile", None)
        self.local_path = self.get_local_path()
        self.description = "{} file".format(action)
        if desc:
            self.description = desc.strip()
        from .constants import STATUS_MAP, ACTION_MAP
        self.status_dict = STATUS_MAP
        self.action_dict = ACTION_MAP

    def run(self):
        """
        Run the action
        1. Create a new changelist
        2. Add file to the changelist
        3. Run the action
        4. Submit the action
        5. Update sg_item and return it
        """
        # Create a new changelist
        #self.change = self.create_change_list()
        # Add file to the changelist
        add_res = self.add_file_to_change_list()
        # Perform the action
        perform_res = self.perform_action()
        #  Submit the changelist to Perforce
        # submit = self.submit_change()
        # Update sg_item
        self.update_sg_item()

        return self.sg_item


    def create_change_list(self):
        """
        Create a new changelist
        """
        change_res = create_change(self.p4, self.description)
        logger.debug(">>>> change_res: {}".format(change_res))
        return change_res

    def add_file_to_change_list(self):
        """
        Add file to the changelist
        """
        add_res = None

        #if self.depot_file:
        if self.local_path:
            # add_res = add_to_change(self.p4, self.change, self.depot_file)
            add_res = add_to_change(self.p4, self.change, self.local_path)

            #add_res = add_to_default_changelist(self.p4, self.local_path)
            logger.debug(">>>> add_res: {}".format(add_res))
        return add_res

    def perform_action(self):
        """
        Perform the action
        """
        action_result = None
        action = self.action_dict.get(self.action, None)
        if action:
            action_result = self.p4.run(action, "-c", self.change, "-v", self.local_path)
            # action_result = self.p4.run(action, "-c", self.change, "-v", self.depot_file)
            logger.debug(">>>> In perform_action: action_result: {}".format(action_result))
        return action_result


    def submit_change(self):
        """
        Submit the changelist to Perforce
        """
        submit = submit_change(self.p4, self.change)
        logger.debug(">>>> submit result is: {}".format(submit))
        return submit

    def update_sg_item(self):
        """
        Update sg_item
        """
        self.sg_item["headChange"] = self.change
        self.sg_item["sg_status_list"] = self.get_p4_status(self.action)
        self.sg_item["action"] = self.action
        self.sg_item["description"] = self.description
        fstat = self.get_fstat_info()
        if fstat:
            self.sg_item["headRev"] = fstat.get("headRev", None)

    def get_p4_status(self, p4_status):

        p4_status = p4_status.lower()
        sg_status = self.status_dict.get(p4_status, None)
        # logger.debug("p4_status: {}".format(p4_status))
        # logger.debug("sg_status: {}".format(sg_status))
        return sg_status

    def get_fstat_info(self):
        fstat = None
        fstat_list = self.p4.run("fstat", self.depot_file)
        if fstat_list:
            fstat = fstat_list[0]
        return fstat

    def get_local_path(self):
        local_path = None
        if "local_path" in self.sg_item["path"]:
            local_path = self.sg_item["path"].get("local_path", None)
        return local_path




