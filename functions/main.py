import os
import json
import logging
import shotgun_api3
import gspread
from firebase_functions import https_fn
from flask import Request, jsonify, redirect
from googleapiclient.discovery import build
from google.oauth2 import service_account

"""
Load Google Sheets & ShotGrid Credentials
"""

google_sheet_credentials_path = os.path.join(os.path.dirname(__file__), "willow.json")

if not os.path.exists(google_sheet_credentials_path):
    raise RuntimeError(f'Google Sheet credentials file "willow.json" not found at {google_sheet_credentials_path}')

try:
    with open(google_sheet_credentials_path, "r") as f:
        credentials = json.load(f)  #  Load JSON credentials
        sg_api_key = credentials.get("sg_api_key")  #  Fetch ShotGrid API Key
        if not sg_api_key:
            raise ValueError("ShotGrid API Key is missing from willow.json")
    sa = gspread.service_account_from_dict(credentials)  #  Authenticate Google Sheets
except Exception as e:
    raise RuntimeError(f"Failed to authenticate credentials: {str(e)}")

"""
Connect to ShotGrid
"""
def get_shotgrid_connection():
    SHOTGUN_URL = "YOUR SHOTGRID WEBSITE URL"
    SCRIPT_NAME = "YOUR SCRIPT NAME ON SHOTGRID"
    SCRIPT_KEY = sg_api_key  #  Use retrieved secret

    try:
        sg = shotgun_api3.Shotgun(SHOTGUN_URL, SCRIPT_NAME, SCRIPT_KEY)
        return sg
    except Exception as e:
        logging.error(f"Failed to connect to ShotGrid: {str(e)}")
        return None

"""
Firebase Function for Syncing Notes to ShotGrid
"""
@https_fn.on_request()
def sync_notes_to_shotgrid(request: Request):
    """Handler function that receives requests from Google Apps Script"""
    if request.method != "POST":
        return jsonify({"error": "Method not allowed. Use POST."}), 405

    # Log request headers and body
    logging.info(f"Received notes sync request headers: {request.headers}")

    raw_data = request.data.decode("utf-8").strip()  # Ensure it's not empty
    logging.info(f"Raw notes sync request body: {raw_data}")

    try:
        request_json = request.get_json(silent=True)
        if not request_json:
            return jsonify({"error": "No JSON data provided"}), 400

        logging.info(f"Notes sync JSON payload: {json.dumps(request_json, indent=2)}")

        # Extract spreadsheet ID and user email from request
        spreadsheet_id = request_json.get('spreadsheetId')
        user_email = request_json.get('userEmail')
        sheet_name = request_json.get('sheetName', 'Notes Back')

        # Validate required parameters
        if not spreadsheet_id:
            return jsonify({"error": "Missing required parameter: spreadsheetId"}), 400

        logging.info(f"Processing notes sync request from {user_email} for spreadsheet {spreadsheet_id}, sheet {sheet_name}")

        # Connect to ShotGrid
        sg = get_shotgrid_connection()
        if not sg:
            return jsonify({"error": "Failed to connect to ShotGrid"}), 500

        # Call the actual implementation function with extracted parameters
        result = process_notes_sync(sg, spreadsheet_id, sheet_name, user_email)

        if not result["success"]:
            return jsonify({
                "status": "error",
                "message": result["message"]
            }), 500

        return jsonify({
            "status": "success",
            "message": "Notes synced to ShotGrid successfully",
            "spreadsheetId": spreadsheet_id,
            "userEmail": user_email,
            "details": result.get("details", {})
        }), 200

    except Exception as e:
        logging.error(f"Error in sync_notes_to_shotgrid: {str(e)}")
        return jsonify({"error": f"Failed to process request: {str(e)}"}), 500

"""
Firebase Function for Playlist to Sheets
"""
@https_fn.on_request()
def sync_playlist_to_google_sheets(request: Request):
    if request.method != "POST":
        return jsonify({"error": "Method not allowed. Use POST."}), 405

    # Log request headers and body
    logging.info(f"Received request headers: {request.headers}")

    raw_data = request.data.decode("utf-8").strip()  # Ensure it's not empty
    logging.info(f"Raw request body: {raw_data}")

    request_json = None  # Initialize JSON storage

    # Try parsing JSON (if the request is sent as JSON)
    if raw_data:
        try:
            request_json = request.get_json(silent=True)
            logging.info(f"Received JSON payload: {json.dumps(request_json, indent=2)}")
        except Exception as e:
            logging.warning(f"Failed to parse JSON body: {str(e)}")

    # Extract parameters from form data (if present)
    selected_ids = request.form.get("selected_ids")
    project_name = request.form.get("project_name")
    user_login = request.form.get("user_login")

    # If JSON exists, override with JSON data (ShotGrid sometimes sends JSON instead)
    if request_json:
        selected_ids = request_json.get("selected_ids", selected_ids)
        project_name = request_json.get("project_name", project_name)
        user_login = request_json.get("user_login", user_login)

    # Log extracted values
    logging.info(f"Extracted selected_ids: {selected_ids}")
    logging.info(f"Extracted project_name: {project_name}")
    logging.info(f"Extracted user_login: {user_login}")

    # Validate required parameters
    if not selected_ids:
        return jsonify({"error": "Missing 'selected_ids'", "received_data": raw_data}), 400
    if not project_name:
        return jsonify({"error": "Missing 'project_name'", "received_data": raw_data}), 400

    # Convert selected_ids to a list (ShotGrid may send a comma-separated string)
    selected_ids = selected_ids.split(",") if isinstance(selected_ids, str) else selected_ids
    if not selected_ids or not selected_ids[0].isdigit():
        return jsonify({"error": "Invalid or missing selected playlist ID", "received_data": raw_data}), 400

    playlist_id = int(selected_ids[0])  # Convert first ID to integer

    logging.info(f"Processing playlist_id: {playlist_id}, project_name: {project_name}")

    template_sheet_id = "https://docs.google.com/spreadsheets/d/1MjhyLz6LmmsFQBFMFQj37srRK95ksbl91wiz3a0hNTY/edit?gid=426049621#gid=426049621"  # Hardcoded Sheet Template ID

    """
    Connect to ShotGrid
    """
    SHOTGUN_URL = "YOUR SG SITE URL"
    SCRIPT_NAME = "YOUR SG SCRIPT NAME"
    SCRIPT_KEY = sg_api_key  #  Use retrieved secret

    try:
        sg = shotgun_api3.Shotgun(SHOTGUN_URL, SCRIPT_NAME, SCRIPT_KEY)
    except Exception as e:
        return jsonify({"error": f"Failed to connect to ShotGrid: {str(e)}"}), 500

    """
    Find Playlist
    """
    try:
        playlist = sg.find_one("Playlist", [["id", "is", playlist_id]], ["code"])
        if not playlist:
            return jsonify({"error": f"No playlist found with ID: {playlist_id}"}), 404
        playlist_name = playlist["code"]
    except Exception as e:
        return jsonify({"error": f"Error finding playlist: {str(e)}"}), 500

    """
    Find Project Frame Handles
    """
    try:
        project = sg.find_one("Project", [["name", "is", project_name]], ["sg_frame_handles"])
        project_frame_handles = project.get("sg_frame_handles") if project else None
        logging.info(f"Project frame handles: {project_frame_handles}")
    except Exception as e:
        logging.error(f"Error finding project frame handles: {str(e)}")
        project_frame_handles = None

    """
    Find Versions with additional fields
    """
    filters = [
        ["playlists", "in", [{"type": "Playlist", "id": playlist_id}]],
        ["project.Project.name", "is", project_name]
    ]
    fields = [
        "sg_shot_code", "client_code", "code", "sg_work_description",
        "entity", "sg_status_list", "sg_first_frame", "sg_last_frame",
        "sg_slate_notes"  # Added slate notes field
    ]

    try:
        versions = sg.find("Version", filters, fields)
        if not versions:
            return jsonify({"error": f"No versions found for playlist {playlist_name}"}), 404
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    """
    Clone Template and Create New Sheet
    """
    try:
        drive_credentials = service_account.Credentials.from_service_account_file(
            google_sheet_credentials_path,
            scopes=["https://www.googleapis.com/auth/drive"]
        )
        drive_service = build("drive", "v3", credentials=drive_credentials)
        #  Copy template to create a new sheet
        new_sheet = drive_service.files().copy(
            fileId=template_sheet_id,
            body={"name": f"{playlist_name}"}
        ).execute()
        new_sheet_id = new_sheet["id"]

        #  Share the Sheet with workspace domain
        domain_permission = {
            "type": "domain",
            "role": "writer",  # "writer" grants edit access
            "domain": "YOUR EMAIL DOMAIN"  #  Change this to your actual workspace domain
        }
        drive_service.permissions().create(
            fileId=new_sheet_id,
            body=domain_permission,
            fields="id"
        ).execute()

        #  Share the Sheet with "anyone with the link" (view access)
        anyone_permission = {
            "type": "anyone",
            "role": "writer",
            "allowFileDiscovery": False  # This means it won't appear in public search results
        }
        drive_service.permissions().create(
            fileId=new_sheet_id,
            body=anyone_permission,
            fields="id"
        ).execute()

        logging.info(f"Created and shared sheet with ID: {new_sheet_id}")

    except Exception as e:
        return jsonify({"error": f"Failed to create and share Google Sheet: {str(e)}"}), 500

    try:
        # Open the spreadsheet
        spreadsheet = sa.open_by_key(new_sheet_id)

        # Get the main sheet (submission)
        submission_sheet = spreadsheet.sheet1  # Main sheet (usually named "Submission")

        # Get or create the "Notes Back" sheet
        notes_back_sheet = None
        try:
            notes_back_sheet = spreadsheet.worksheet("Notes Back")
            logging.info("Found existing 'Notes Back' sheet")
        except gspread.exceptions.WorksheetNotFound:
            # Create the sheet if it doesn't exist
            notes_back_sheet = spreadsheet.add_worksheet(title="Notes Back", rows=1000, cols=26)
            logging.info("Created new 'Notes Back' sheet")
    except Exception as e:
        return jsonify({"error": f"Could not open or create sheets: {str(e)}"}), 500

    """
    Fetch & Sort Versions
    """

    logging.info(f"ShotGrid Versions Data: {json.dumps(versions, indent=2)}")

    sorted_versions = sorted(versions, key=lambda x: x.get("sg_shot_code", ""))

    """
    Find Client Notes Using Shot Entities and Content Search
    """

    # Initialize empty mapping
    latest_notes_map = {}

    try:
        # Get a list of all shot entities from our versions
        shot_entities = []

        for version in sorted_versions:
            # Get the shot entity if it exists
            entity = version.get("entity")
            if entity and entity.get("type") == "Shot" and entity not in shot_entities:
                shot_entities.append(entity)

        logging.info(f"Found {len(shot_entities)} unique shot entities")

        # For each shot entity, find notes containing "client note" (case insensitive)
        for shot_entity in shot_entities:
            shot_id = shot_entity["id"]

            # Get shot code for this entity to map back to versions
            shot = sg.find_one("Shot", [["id", "is", shot_id]], ["code"])

            if not shot or not shot.get("code"):
                logging.warning(f"Could not find shot code for shot ID: {shot_id}")
                continue

            shot_code = shot["code"]
            logging.info(f"Processing shot: {shot_code} (ID: {shot_id})")

            # Search for notes linked to this shot
            try:
                # First try to find notes with "client note" in the content
                note_filters = [
                    ["note_links", "is", shot_entity],
                    ["content", "contains", "client note"]  # Case insensitive by default
                ]

                client_notes = sg.find(
                    "Note",
                    note_filters,
                    ["content", "created_at"],
                    order=[{"field_name": "created_at", "direction": "desc"}],
                    limit=1  # Only get the most recent
                )

                # If no notes found, try without "client note" filter
                if not client_notes:
                    logging.info(f"No notes with 'client note' found for {shot_code}, getting all notes")
                    note_filters = [["note_links", "is", shot_entity]]

                    client_notes = sg.find(
                        "Note",
                        note_filters,
                        ["content", "created_at"],
                        order=[{"field_name": "created_at", "direction": "desc"}],
                        limit=1  # Only get the most recent
                    )

                # If notes found, save the most recent one
                if client_notes:
                    latest_note = client_notes[0]
                    note_content = latest_note.get("content", "")

                    if note_content:
                        logging.info(f"Found note for {shot_code}: {note_content[:50]}...")
                        latest_notes_map[shot_code] = note_content
                    else:
                        logging.warning(f"Note found for {shot_code} but content is empty")
                else:
                    logging.info(f"No notes found for {shot_code}")

            except Exception as e:
                logging.error(f"Error fetching notes for shot {shot_code}: {str(e)}")
                # Continue with next shot

        logging.info(f"Successfully fetched notes for {len(latest_notes_map)} shots")

    except Exception as e:
        logging.error(f"Error in client notes processing: {str(e)}")
        # Continue with empty notes map

    """
    Sort & Prepare Data for Sheets
    """

    try:
        # Prepare data for main submission sheet (with adjusted columns - removed column E)
        submission_data = []
        frame_counts = []  # Store frame counts for column I (moved from J)
        handles_values = []  # Store handles values for column J (moved from K)
        combined_status_slate = []  # Store combined status and slate notes for column K (moved from L)

        # Prepare data for Notes Back sheet
        notes_back_data = []

        for version in sorted_versions:
            shot_code = version.get("sg_shot_code", "")
            version_code = version.get("code", "")  # This will go to Notes Back sheet

            # Get status and map it to the proper display value
            status = version.get("sg_status_list", "")
            formatted_status = ""

            # Convert status codes to readable text
            if status:
                # Map only specific ShotGrid status codes
                status_map = {
                    "sndv0": "v000",
                    "sndwip": "WIP",
                    "sndcli": "For Final",
                    "apv": "Delivery",
                    "note": "Client Note",
                    "di": "Delivered"
                }

                # Use mapped status name if available, otherwise use the status code
                formatted_status = status_map.get(status, status)

            # Calculate frame count: (last_frame - first_frame) + 1
            first_frame = version.get("sg_first_frame")
            last_frame = version.get("sg_last_frame")
            frame_count = ""

            if first_frame is not None and last_frame is not None:
                try:
                    frame_count = str(int(last_frame) - int(first_frame) + 1)
                    logging.info(f"Calculated frame count for {shot_code}: {frame_count}")
                except (ValueError, TypeError) as e:
                    logging.warning(f"Failed to calculate frame count for {shot_code}: {str(e)}")

            # Get slate notes and combine with status for column K
            slate_notes = version.get("sg_slate_notes", "")
            combined_value = f"{formatted_status} - {slate_notes}" if slate_notes else f"{formatted_status} - "

            # Store values for separate column updates
            frame_counts.append([frame_count])
            handles_values.append([str(project_frame_handles) if project_frame_handles is not None else ""])
            combined_status_slate.append([combined_value])

            # Add row data for submission sheet (C-G) - Removed column E (Version Code)
            submission_data.append([
                shot_code,                           # Column C - Shot Code
                version.get("client_code", ""),      # Column D - Version Name
                version.get("sg_work_description", ""), # Column E - Work Description (moved from F)
                latest_notes_map.get(shot_code, ""), # Column F - Latest Client Note (moved from G)
                formatted_status                     # Column G - Submitted For (moved from H)
            ])

            # Add row data for Notes Back sheet - only version code in column A
            notes_back_data.append([
                version_code                         # Column A - Version Code (without Shot Code)
            ])

        # Log what we're updating
        logging.info(f"Updating submission sheet with {len(submission_data)} rows of data")
        logging.info(f"Updating Notes Back sheet with {len(notes_back_data)} rows of data")

        # Update submission sheet in multiple batch operations
        if submission_data:
            start_row = 2  # Start from row 2 (after header)
            end_row = start_row + len(submission_data) - 1

            # 1. Update columns C-G with version data
            submission_sheet.update(f"C{start_row}:G{end_row}", submission_data)

            # 2. Add playlist name to column B for every row with data
            playlist_name_column = [[playlist_name]] * len(submission_data)
            submission_sheet.update(f"B{start_row}:B{end_row}", playlist_name_column)

            # 3. Update column I with frame counts (moved from J)
            submission_sheet.update(f"I{start_row}:I{end_row}", frame_counts)

            # 4. Update column J with project handles (moved from K)
            submission_sheet.update(f"J{start_row}:J{end_row}", handles_values)

            # 5. Update column K with combined status and slate notes (moved from L)
            submission_sheet.update(f"K{start_row}:K{end_row}", combined_status_slate)

        # Update Notes Back sheet
        if notes_back_data:
            # Update data starting from row 2 (no header, as it will be set in the template)
            notes_back_sheet.update(f"A2:A{1 + len(notes_back_data)}", notes_back_data)

    except Exception as e:
        logging.error(f"Failed to update Google Sheets: {str(e)}")
        return jsonify({"error": f"Failed to update Google Sheets: {str(e)}"}), 500

    """
    Send Back URL
    """
    sheet_url = f"https://docs.google.com/spreadsheets/d/{new_sheet_id}"
    return redirect(sheet_url, code=302)

    """
    Send Notes to Flow
    """

def process_notes_sync(sg, spreadsheet_id, sheet_name, user_email):
    """
    Processes the notes from Google Sheets and syncs them to ShotGrid

    Fetches columns:
    - A: Version code
    - D: Version status
    - E: Note body
    - F: Links (containing Shot and Version information)

    Converts status labels to ShotGrid status codes:
    - "Client Note" -> "note"
    - "Client Approved" -> "apv"
    - "Hero Shot" -> "hero"

    Uses Google user email as the author to be linked in ShotGrid

    After processing, highlights processed cells in lime green

    Args:
        sg: ShotGrid connection object
        spreadsheet_id: ID of the Google Sheet
        sheet_name: Name of the sheet containing notes (default: 'Notes Back')
        user_email: Email of the user who triggered the sync (used as note author)

    Returns:
        Dictionary containing success status and additional information
    """
    try:
        logging.info(f"Processing notes sync for sheet: {sheet_name} in spreadsheet: {spreadsheet_id}")

        # Open the spreadsheet using gspread
        spreadsheet = sa.open_by_key(spreadsheet_id)
        worksheet = spreadsheet.worksheet(sheet_name)

        # Get all values (including headers)
        all_values = worksheet.get_all_values()

        if len(all_values) <= 1:  # Only headers or empty sheet
            return {
                "success": False,
                "message": f"No data found in sheet '{sheet_name}' (only headers or empty)"
            }

        # Extract headers and data rows
        headers = all_values[0]
        data_rows = all_values[1:]

        # Find the indices for columns A, D, E, and F
        # Even though we expect them to be 0, 3, 4, 5, we'll search for them by header name
        # to be more robust against sheet changes
        try:
            version_col = headers.index("Version Code")  # Column A
            status_col = headers.index("Version Status")         # Column D
            note_col = headers.index("Body")             # Column E
            links_col = headers.index("Links")           # Column F
        except ValueError as e:
            # If any expected headers are missing
            logging.error(f"Missing required column header: {str(e)}")
            return {
                "success": False,
                "message": f"Missing required column headers in sheet '{sheet_name}'. Expected: Version Code, Version Status, Body, Links"
            }

        # Status mapping from sheet labels to ShotGrid status codes
        status_mapping = {
            "Client Note": "note",
            "Client Approved": "apv",
            "Hero Shot": "hero",
        }

        # Create an array of note data to process
        notes_to_sync = []
        processed_rows = 0
        skipped_rows = 0

        # Keep track of row indices for cells to highlight later
        row_indices_to_highlight = []

        for idx, row in enumerate(data_rows):
            # Skip empty rows or rows without required data
            if len(row) <= max(version_col, status_col, note_col, links_col):
                skipped_rows += 1
                continue

            version_code = row[version_col].strip()
            status_label = row[status_col].strip()
            note_body = row[note_col].strip()
            links = row[links_col].strip()

            # Skip rows with no version code or note body
            if not version_code or not note_body:
                skipped_rows += 1
                continue

            # Store the row index (add 2 because idx is 0-based and we need to account for header row)
            row_index = idx + 2
            row_indices_to_highlight.append(row_index)

            # Convert status label to status code
            status_code = status_mapping.get(status_label, status_label)

            notes_to_sync.append({
                "version_code": version_code,
                "status_label": status_label,
                "status_code": status_code,
                "note_body": note_body,
                "links": links,
                "author_email": user_email,
                "row_index": row_index
            })
            processed_rows += 1

        if not notes_to_sync:
            return {
                "success": False,
                "message": f"No valid note data found in sheet '{sheet_name}'"
            }

        logging.info(f"Found {len(notes_to_sync)} valid notes to sync to ShotGrid")

        # Process each note and send to ShotGrid
        success_count = 0
        failed_notes = []
        successful_row_indices = []

        for note_data in notes_to_sync:
            try:
                # 1. Find the Version entity by code
                version = sg.find_one("Version", [["code", "is", note_data["version_code"]]],
                                      ["id", "entity", "project"])

                if not version:
                    logging.warning(f"Version not found: {note_data['version_code']}")
                    failed_notes.append({
                        "version_code": note_data["version_code"],
                        "error": "Version not found in ShotGrid"
                    })
                    continue

                # 2. Find the ShotGrid user by email
                sg_user = sg.find_one("HumanUser", [["email", "is", note_data["author_email"]]], ["id"])

                if not sg_user:
                    # Try to find by username (email without domain)
                    username = note_data["author_email"].split('@')[0]
                    sg_user = sg.find_one("HumanUser", [["login", "is", username]], ["id"])

                if not sg_user:
                    logging.warning(f"User not found for email: {note_data['author_email']}")
                    # Continue with script user instead of failing
                    sg_user = {"type": "ApiUser", "id": 1}  # Default to API script user

                # 3. Build note links (always link to Version; link to Shot if available)
                note_links = [{"type": "Version", "id": version["id"]}]

                # If version has a linked entity (Shot), add it to note_links
                if version.get("entity") and version["entity"].get("type") == "Shot":
                    note_links.append(version["entity"])

                # 4. Create the note in ShotGrid
                new_note = {
                    "project": version.get("project"),
                    "content": note_data["note_body"],
                    "note_links": note_links,
                    "user": sg_user
                }

                # Create the note
                created_note = sg.create("Note", new_note)
                logging.info(f"Created note with ID: {created_note['id']} for version: {note_data['version_code']}")

                # 5. Update version status if a status was provided
                if note_data["status_code"]:
                    try:
                        status_update = {
                            "sg_status_list": note_data["status_code"]
                        }
                        sg.update("Version", version["id"], status_update)
                        logging.info(f"Updated version {note_data['version_code']} status to {note_data['status_code']}")
                    except Exception as status_err:
                        logging.warning(f"Failed to update version status: {str(status_err)}")
                        # Don't count this as a complete failure since the note was created

                success_count += 1
                successful_row_indices.append(note_data["row_index"])

            except Exception as e:
                logging.error(f"Error processing version {note_data['version_code']}: {str(e)}")
                failed_notes.append({
                    "version_code": note_data["version_code"],
                    "error": str(e)
                })

        # Highlight cells in lime green for successfully processed rows
        if successful_row_indices:
            try:
                # Determine columns to highlight based on version_col, status_col, note_col, links_col
                columns_to_highlight = [version_col, status_col, note_col, links_col]

                # Get the column letters for these indices
                column_letters = [chr(65 + col_idx) for col_idx in columns_to_highlight]  # A=65 in ASCII

                # Create batch requests for formatting
                for row_idx in successful_row_indices:
                    for col_letter in column_letters:
                        cell_range = f"{col_letter}{row_idx}"

                        # Define the lime green color
                        lime_green = {
                            "red": 0.0,
                            "green": 1.0,
                            "blue": 0.35
                        }

                        # Apply formatting
                        worksheet.format(cell_range, {
                            "backgroundColor": lime_green
                        })

                logging.info(f"Successfully highlighted {len(successful_row_indices)} rows in lime green")

            except Exception as highlight_err:
                logging.warning(f"Failed to highlight cells: {str(highlight_err)}")
                # Don't count this as a complete failure

        # Return result with counts and status
        return {
            "success": True,
            "message": f"Processed {len(notes_to_sync)} notes: {success_count} succeeded, {len(failed_notes)} failed",
            "details": {
                "total_rows": len(data_rows),
                "processed_rows": processed_rows,
                "skipped_rows": skipped_rows,
                "success_count": success_count,
                "failed_count": len(failed_notes),
                "failed_notes": failed_notes[:10] if failed_notes else [],  # Limit to first 10 failures
                "processed_by": user_email,
                "highlighted_rows": len(successful_row_indices),
                "status_conversions": {k: v for k, v in status_mapping.items() if k in [n["status_label"] for n in notes_to_sync]}
            }
        }

    except Exception as e:
        logging.error(f"Error in process_notes_sync: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to sync notes: {str(e)}"
        }
