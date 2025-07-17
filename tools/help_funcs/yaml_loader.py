import yaml

def load_params(yaml_path):
    with open(yaml_path, "r") as f:
        params = yaml.safe_load(f)
    return params