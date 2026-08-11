"""
Stage 05: load raw pickle
Extracted verbatim from the original monolithic data_cleaning.py (source lines 1179-1207). Logic is unchanged; this file is executed as one stage of the pipeline by run_pipeline.py, sharing a single namespace across all stages so variable state flows exactly as it did in the original script.
"""

# 5. Load the raw drive-test pickle
# =========================

if not DRIVE_TEST_PATH.exists():
    raise FileNotFoundError(
        f"Raw drive-test file was not found at {DRIVE_TEST_PATH}. "
        "Place Network_Drive_Test.pkl inside Raw_Data/ and rerun."
    )

drive_raw_obj = pd.read_pickle(DRIVE_TEST_PATH)

# Some pickle exports may store a dict of tables instead of a direct DataFrame.
# If that happens, select the largest DataFrame as the drive-test table.
if isinstance(drive_raw_obj, pd.DataFrame):
    drive_raw = drive_raw_obj.copy()
elif isinstance(drive_raw_obj, dict):
    dataframe_items = {k: v for k, v in drive_raw_obj.items() if isinstance(v, pd.DataFrame)}
    if not dataframe_items:
        raise ValueError("The pickle contains a dict, but no pandas DataFrame values were found.")
    selected_key = max(dataframe_items, key=lambda k: dataframe_items[k].shape[0] * dataframe_items[k].shape[1])
    print(f"Pickle contains multiple tables. Selected largest DataFrame key: {selected_key}")
    drive_raw = dataframe_items[selected_key].copy()
else:
    raise TypeError(f"Unsupported pickle object type: {type(drive_raw_obj)}")

overview(drive_raw, "Raw drive-test data")


# =========================
