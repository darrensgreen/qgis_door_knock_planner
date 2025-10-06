# README


# User Guide: Door Knock Route Planner

### 1. Introduction

The Door Knock Route Planner is a QGIS plugin designed to help plan and
organise door-knocking campaigns for disaster management, major
investigations, or search and rescue operations.

It takes a list of addresses, divides them among a specified number of
field crews, and calculates the most efficient, ordered route for each
crew to follow from a central starting point.

### 2. Before You Begin: Data Preparation

For the planner to work effectively, you need three essential data
layers ready in your QGIS project. Using up-to-date and accurate data is
highly recommended for the best results.

1.  **Area of Interest (Polygon Layer):** A polygon layer that defines
    the boundary of your operation (e.g., a suburb, a flood extent area,
    a search grid).

2.  **Address Points (Point Layer):** A point layer containing all the
    potential addresses to be visited. **Recommended (Australia):** For
    best results, use the latest version of the Geocoded National
    Address File (GNAF), available from
    [data.gov.au](https://data.gov.au/data/dataset/geocoded-national-address-file-g-naf).

3.  **Road Network (Line Layer):** A line layer representing the streets
    and roads the crews can travel on.

    1.  **Option A - Use Official State Data (Recommended):** For
        operations in Queensland, Australia, the authoritative
        **Queensland Roads and Tracks** dataset is recommended,
        available from
        [data.qld.gov.au](https://www.data.qld.gov.au/dataset/queensland-roads-and-tracks).

    2.  **Option B - Download from OpenStreetMap (Alternative Method):**
        If you do not have a road network file, you can download live
        data from OpenStreetMap directly within QGIS using the
        **QuickOSM** plugin. **How to use QuickOSM:**

        1.  Make sure your Area of Interest or flood model layer is
            loaded and visible on the map canvas.

        2.  Click the **QuickOSM** plugin icon in the toolbar.

        3.  In the QuickOSM window, go to the **Quick query** tab.

        4.  In the `Key` field, type `highway`. Leave the `Value` field
            blank to select all road types.

        5.  Click the dropdown menu that says `In` and change it to
            **Layer Extent**.

        6.  Select your Area of Interest or flood model layer from the
            adjacent dropdown menu.

        7.  Click **Run query**.

        **Note:** The larger the area, the longer this query will take.
        The plugin will download all roads within the boundary of your
        selected layer and add them to your map.

### 3. Step-by-Step: Running the Planner

1.  **Open the Tool:** In QGIS, open the **Processing Toolbox** panel
    (`View > Panels > Processing Toolbox`). Find the **Door Knock
    Planner** provider and double-click the **Door Knock Route Planner**
    algorithm.
2.  **Fill in the Parameters:**
    - **Area of Interest (Polygon):** Select your boundary polygon
      layer.
    - **Address Points:** Select your address point layer.
    - **Road Network:** Select your road network layer (either from an
      official file or the `highway` layer downloaded from QuickOSM).
    - **Start Location:** Click the `...` button to the right of the
      field. Your cursor will turn into a crosshair. Click on the map to
      set the starting point for all crews.
    - **Number of Available Crews:** Enter the number of teams you have
      available.
3.  **Run the Algorithm:** Click the **Run** button.

### 4. Understanding the Outputs

The tool will create two new layers:

- **Visit Points (Ordered):** A point layer showing the addresses to be
  visited. Its Attribute Table contains `crew_id`, `visit_order`, and
  `cost` (travel time/distance) fields to guide the crews.
- **Door Knock List (Table):** A non-spatial table formatted for easy
  export to a CSV file for use in the field. To export, right-click the
  layer, select `Export > Save Features As...`, and choose “Comma
  Separated Value \[CSV\]”.

### 5. How to Apply a Prioritisation Method

The Route Planner works on the specific set of addresses you provide. To
prioritise visits (e.g., focus on low-lying areas first), you must first
filter your address layer *before* running the planner.

**Method 1: Prioritising by Elevation (for Flood Events)** This method
ranks addresses by their elevation to identify those likely to be
impacted first by rising floodwaters.

1.  **Get Elevation Data:** Use the **Sample raster values** tool from
    the Processing Toolbox to add elevation data from a DEM (like Mapzen
    Global Terrain) to your address points.

2.  **Create Priority Ranks:** Use the **Field Calculator** on the new
    `Sampled` layer to create a new text field (e.g., `Priority_Rank`).
    Use a `CASE` statement to group addresses into elevation bands
    (e.g., ‘1: 0 - 10m’, ‘2: 11 - 20m’, etc.).

3.  **Filter and Run:** Right-click your `Sampled` layer, choose
    **Filter…**, and enter an expression to show only the
    highest-priority addresses (e.g., `"Priority_Rank" = '1: 0 - 10m'`).
    Then, run the **Door Knock Route Planner**, using this filtered
    layer as your **Address Points** input.

**Method 2: Prioritising by Proximity (for Investigations or SAR)** This
method ranks addresses based on their distance from a key location, such
as a crime scene or a missing person’s Last Known Point (LKP).

1.  **Create a Point of Interest:** Create a new temporary point layer
    and add a single point at your location of interest.

2.  **Create Distance Buffers:** Use the **Buffer** tool to create
    concentric rings (e.g., at 100m, 200m, 300m) around your Point of
    Interest.

3.  **Assign Proximity Ranks:** Use the **Join attributes by location**
    tool to transfer the buffer distance attribute to each address point
    that falls within a ring.

4.  **Filter and Run:** **Filter** the resulting `Joined layer` to show
    only addresses within a specific distance (e.g.,
    `"distance" = 100`). Run the **Door Knock Route Planner** using this
    filtered layer as your **Address Points** input.

### 6. Important Considerations

- **Performance:** This tool is data-heavy. For best performance, use it
  on a localised area. Running on very large datasets may cause QGIS to
  freeze.
- **Live Events:** The network analysis does **not** account for
  real-time road closures from flooding or other hazards. During a live
  event, you may need to break your area into smaller, accessible zones
  and run the planner for each one.
- **Incomplete Routes:** If the output shows a “NULL” `cost` for some
  addresses, it means a route could not be found. This usually happens
  if your road network layer is incomplete. Try downloading a larger
  road network extent.
