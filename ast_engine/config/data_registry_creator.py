'''
Set up dict structure and import spreadsheet datasets into pydantic model

'''

# %%
from wip_pydantic_structure import RegistryDatasets

import pandas as pd

import yaml

# %%

input_xlsx = r"registry\Test_Registry.xlsx"
yaml_path = r"registry\datasets.yaml"

template_outer_dict = {
    "registry_ver": 0.1,
    "datasets":[

    ],
}

template_inner_dict = {
    # id: id
    "name": "Featureclass_Name(valid characters only)",
    # "unique_id": "OBJECTID",
    # "adapter_type": data_type, # Based on data source, will require logic to interpret
    "datasource": {
        "layer": "Datasource" # The path to the dataset
    },
    "columns": [
        "Fields_to_Summarize",
        "Fields_to_Summarize2",
        "Fields_to_Summarize3",
        "Fields_to_Summarize4",
        "Fields_to_Summarize5",
        "Fields_to_Summarize6",
    ],
    "definition":"Definition_Query",
    "geom": {
        # "geom_column": GEOMETRY_col,
        # "geom_type": geom_type,
        # "crs": 4326 # This needs to be a transformation
    },
    # "operators": [
    #     # "overlay",
    #     {
    #         "proximity": {
    #         "distance": "Buffer_Distance"
    #         },
    #     },
    # ]
}

# %%

def val_populator(template_dict, ref_row):
    '''
    Recurses through the dict structure and uses pd to replace strings with spreadsheet values.
    TODO: Where a variable is specified, this will call a named function.
        -Do this as an additional case, likely with lambda functions in the dict
    '''
    from copy import deepcopy
    def recurse_populator(inp_dict, inp_row):
        for key, value in inp_dict.items():
            if isinstance(value, dict): # Recurse into dict
                recurse_populator(value, inp_row)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict): # Recurse into dict
                        recurse_populator(item, inp_row)
                    else:
                        if pd.isna(inp_row[item]):
                            inp_dict[key][value.index(item)] = None
                        else:
                            inp_dict[key][value.index(item)] = inp_row[item]
            else:
                if pd.isna(inp_row[value]):
                    inp_dict[key] = None
                else:
                    inp_dict[key] = inp_row[value]
    out_dict = deepcopy(template_dict) # To separate from template
    recurse_populator(out_dict, ref_row)
    return out_dict

# %%

df = pd.read_excel(input_xlsx)

for index, row in df.iterrows():
    if pd.notna(row["Featureclass_Name(valid characters only)"]): # check for unnamed rows
        new_dataset = val_populator(template_inner_dict, row)
        new_dataset["id"] = index
        new_dataset["unique_id"] = "OBJECTID"
        new_dataset["adapter_type"] = "kml"
        new_dataset["geom"] = {"geom_column":"foo", "geom_type":"point", "crs":1}
        template_outer_dict["datasets"].append(new_dataset)
# %%

registry_model = RegistryDatasets.model_validate(template_outer_dict)
registry_json = registry_model.model_dump(mode="json")
# %%

with open(yaml_path, 'w') as yaml_file:
    yaml.dump(
        registry_json, 
        yaml_file, 
        default_flow_style=False,
        sort_keys=False,
        )

# %%
