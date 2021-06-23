# Why overthink it? Module executes once, I can have one global
message_sets: dict[int, dict] = dict()


class MWMessages:
    def __init__(self, mc_messages: dict):
        for key, message_set in message_sets.items():
            if message_set == mc_messages:
                self.mw_id = key
                break
        else:
            self.mw_id = len(message_sets)
            message_sets[self.mw_id] = mc_messages

    def __getitem__(self, item):
        message_sets[self.mw_id].get(item, "============")

    def __iter__(self):
        for key, item in message_sets[self.mw_id].items():
            yield key, item
