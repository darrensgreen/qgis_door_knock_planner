library(DiagrammeR)

grViz("
digraph workflow {
  # --- GRAPH ATTRIBUTES ---
  layout = dot;
  rankdir = TB;
  graph [fontname = 'helvetica', splines=ortho]; # Ortho lines look cleaner for this flow
  node [fontname = 'helvetica', shape = box, style = 'rounded,filled'];
  edge [fontname = 'helvetica'];

  # --- NODES ---
  # Using different fill colors for different types of items
  
  # Data Sources / Outputs
  node [fillcolor = whitesmoke, style='rounded,filled'];
  InitialData [label = 'New Address Data\\n(e.g., from new flood map, SAR area)'];
  VisitPoints [label = 'Visit Points & Routes'];
  UpdatedVisitPoints [label = 'Updated Visit Points Layer\\n(Master list with mixed statuses)'];

  # Tools
  node [fillcolor = lightyellow];
  Planner [label = 'Run: Door Knock Route Planner'];
  Tracker [label = 'Run: Door Knock Status Tracker'];

  # Actors / Manual Steps
  node [fillcolor = lightgreen];
  Crews [label = 'Field Crews Collect Data\\n(via CSV, QField, etc.)'];
  UserFilter [label = 'User Action in QGIS:\\nFilter for incomplete tasks'];


  # --- WORKFLOW & LAYOUT ---

  # Cluster for the first part of the operation
  subgraph cluster_01_planning {
    label = '1. Initial Planning & Field Tasking';
    style = filled;
    fillcolor = 'lightblue';
    
    InitialData -> Planner [label = 'First Run Input'];
    Planner -> VisitPoints;
    VisitPoints -> Crews [label = 'Tasking'];
  }

  # Cluster for the update and re-planning cycle
  subgraph cluster_02_update {
    label = '2. Status Tracking & Re-Planning Cycle';
    style = filled;
    fillcolor = 'moccasin';
    
    Crews -> Tracker [label = 'Completed Field Data'];
    Tracker -> UpdatedVisitPoints;
    UpdatedVisitPoints -> UserFilter;
  }
  
  # This edge creates the crucial loop back to the start of the process
  UserFilter -> Planner [label = 'Input for Next Shift', lhead = cluster_01_planning];

}
")
