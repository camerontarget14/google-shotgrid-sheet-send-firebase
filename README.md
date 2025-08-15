# ShotGrid ↔ Google Sheets Sync (Firebase)

A lightweight integration that enables ShotGrid (SG) users—coordinators and production teams—to:

- Push shot/version data from SG to a Google Sheet
- Collect artist feedback and notes in the sheet
- Send those notes back into ShotGrid

Built with Firebase Cloud Functions (Python), the Shotgun API, and Google Apps Script.

![send](https://bucket.camerontarget.com/sendtogoogle.png)

---

## Breakdown

```
google-shotgrid-sheet-send-main/
├── functions/                     # Firebase backend code (Python)
│   ├── main.py                   # Main Flask handler with SG & GSheets integration
│   ├── requirements.txt          # Python dependencies
│   └── willow.json               # Will contain your secrets (consider secret manager)
├── google_appscript/             # Google Sheets-side logic in JavaScript
│   ├── menu.js                   # Adds UI to the Sheet
│   ├── note_prep.js              # Prepares notes from Sheet content
│   ├── sendNotes.js              # Sends notes back to ShotGrid
│   ├── util.js                   # Shared helpers
│   ├── version_sort.js           # Sorts versions in Sheet
│   └── sheets_cell_formulae.txt # Spreadsheet formulas
├── firebase.json                 # Firebase config
└── README.md                     # Setup instructions
```

---

## Technologies Used

- Firebase Cloud Functions for serverless backend ([Firebase Docs](https://firebase.google.com/docs/functions))
- Shotgun API (`shotgun_api3`) ([SG API Docs](https://help.autodesk.com/view/SGDEV/ENU/))
- ShotGrid Action Menu Item ([ShotGrid Developer Docs – Action Menu Items](https://help.autodesk.com/view/SGDEV/ENU/?guid=SGD_ami_action_menu_items_create_html))
- Google Sheets API via `gspread` ([Google Sheets API Docs](https://developers.google.com/sheets/api))
- Google Apps Script frontend ([Apps Script Docs](https://developers.google.com/apps-script))

---

## Setup Guide

### Backend Setup (Firebase Functions)

1. **Clone the repo** and create a Python virtual environment:
    ```bash
    cd functions
    python3.10 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

2. **Prepare a `.env` file** in the `functions/` directory to store your credentials - example in willow.json:
    ```env
    SG_API_KEY=your_shotgrid_script_key
    SG_URL=https://yourstudio.shotgrid.autodesk.com
    SG_SCRIPT_NAME=your_script_name
    GOOGLE_CREDENTIALS_JSON=path/to/your/google/creds.json
    TEMPLATE_SHEET_URL = https://docs.google.com/spreadsheets/d/1MjhyLz6LmmsFQBFMFQj37srRK95ksbl91wiz3a0hNTY/edit?usp=sharing
    --- THE TEMPLATE SHEET URL is added by default but can be changed in main.py! (make sure to give your service account access!)
    ```

3. **Deploy to Firebase**:
    ```bash
    firebase deploy --only functions
    ```

4. **Check logs** during development and debugging:
    ```bash
    firebase functions:log
    ```

---

### Google Sheets Integration

1. Open your Google Sheet
2. Navigate to `Extensions > Apps Script`
3. Copy over the JavaScript (.gs) files from `google_appscript/`:
    - `menu.js` for the custom Sheet menu
    - `sendNotes.js`, `note_prep.js`, `util.js`, etc.
4. Save the project and click **Deploy > Test deployments** or bind to your function endpoint.

You can set up all your Google Sheets appsript functions as an extension that you can make available via the [google sheets marketplace sdk](https://developers.google.com/workspace/marketplace/overview)

---

## License

MIT License. See `LICENSE` file.
