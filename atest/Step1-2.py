import os
from beep.structure.cli import auto_load


this_dir = os.path.dirname(os.path.abspath(__file__))
cycler_file = os.path.join(this_dir, "Severson-et-al/2017-05-12_6C-50per_3_6C_CH36.csv")

datapath = auto_load(cycler_file)
is_valid, msg = datapath.validate()
print("File is valid: ", is_valid)

datapath.structure()


### ------ datapath.structured_data ------
from matplotlib import pyplot as plt

reg_charge = datapath.structured_data[datapath.structured_data.step_type == 'charge']
print("Mean current for cycle 25: ", reg_charge.current[reg_charge.cycle_index == 25].mean())
print("Number of cycles: ", reg_charge.cycle_index.max())
print("Max charge capacity at cycle 25: ", reg_charge.charge_capacity[reg_charge.cycle_index == 25].max())
plt.plot(
    reg_charge.charge_capacity[reg_charge.cycle_index == 600],
    reg_charge.voltage[reg_charge.cycle_index == 600]
)
plt.show()

import numpy as np
unique_cycles = reg_charge.cycle_index.unique()
selected_cycles = unique_cycles[np.arange(1, len(unique_cycles), 100)]
for i in selected_cycles:#reg_charge.cycle_index.unique():
    plt.plot(
        reg_charge.charge_capacity[reg_charge.cycle_index == i],
        reg_charge.voltage[reg_charge.cycle_index == i],
        label= f"Cycle {i}"
    )
plt.xlabel('Charge Capacity')
plt.ylabel('Voltage')
plt.title('Charge Capacity vs Voltage for All Cycles')
plt.legend()  # Optional: Show the legend
plt.show()


### ------ datapath.structured_summary  ------
plt.plot(
    datapath.structured_summary.cycle_index,
    datapath.structured_summary.energy_efficiency)
plt.show()
plt.plot(
    datapath.structured_summary.cycle_index[1:],
    datapath.structured_summary.energy_efficiency[1:])
plt.show()

# Step 3: Prepare for ML &  train a model

# [Featurization] uses [the structured objects] to calculate statistically and physically relevant quantities
# for the purpose of building predictive ML models.
#
# The objects can be selected and joined for the purposes of training the model,
# or used for predicting individual outcomes.

# beep provides classes such as [BEEPFeaturizer] and [BEEPFeatureMatrix]
# for generating and managing sets of features linked to structured files.

# beep also provides [BEEPLinearModelExperiment], a class
# for training linear ML models on battery data
# and predicting new degradation characteristics.

# Quickstart sections on featurization and ML are coming soon!

# Step 4: Predict battery health