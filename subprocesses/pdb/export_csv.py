import os
import csv
from datetime import datetime
from sharedlib.models import ChannelMetrics


def write_boards_to_csv(boards_dict: dict, filename: str):
    """
    Appends the current state of all boards to the specified CSV file.
    """
    fieldnames = [
        "timestamp",
        "board_id",
        "channel_index",
        "voltage",
        "current",
        "power",
        "temp",
        "toggle",
    ]

    # Check if we need to write a header (only if file doesn't exist)
    file_exists = os.path.isfile(filename)

    # Use mode='a' for Append
    with open(filename, "a", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        for board_id, states in boards_dict.items():
            # Get clean name for the board (e.g., "BMS" instead of <PDBID.BMS: 8>)
            board_label = board_id.name if hasattr(board_id, "name") else str(board_id)

            for index, state in enumerate(states):
                # Only log if it's been updated (optional check)
                # if not state.pending_send: continue

                row = {
                    "timestamp": state.last_updated.strftime("%Y-%m-%d %H:%M:%S.%f"),
                    "board_id": board_label,
                    "channel_index": index,
                }

                if isinstance(state.metric_data, ChannelMetrics):
                    row.update(state.metric_data.to_dict())
                else:
                    # BMS Float case: Put into voltage, set others to 0
                    row["voltage"] = state.metric_data
                    row["current"] = 0.0
                    row["power"] = 0.0
                    row["temp"] = 0.0
                    row["toggle"] = False

                writer.writerow(row)
