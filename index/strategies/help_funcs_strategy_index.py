#this file contains helper functions 

def create_tags(type=None, action=None, sl=None, tp=None):
    tags = []
    if sl is not None:
        tags.append(f"SL:{sl}")
    if tp is not None:
        tags.append(f"TP:{tp}")
    if type is not None:
        tags.append(f"TYPE:{type}")
    if action is not None:
        tags.append(f"ACTION:{action}")
    return tags
