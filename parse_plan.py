import json

data_dict = {}
plan_location = ""  #place your .plan directory location

with open("plan_location", "r", encoding="utf-8") as f:
    data_dict = json.load(f)

#print(json.dumps(data_dict, indent=2))
print("\nHome Position (x, y, z): ")
for value in data_dict["mission"]["plannedHomePosition"]:
    print(value, end=", ")
print("\n")

items = data_dict["mission"]["items"]

count = 0
for item in items:
    print("\nMission Command: ", item["command"])
    params = item["params"]
    print("Latitude:", params[4])
    print("Longitude:", params[5])
    print("Altitude:", params[6])
    print("Hold time:", params[0])

