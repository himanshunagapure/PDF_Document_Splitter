# PDF Document Splitter API

This project provides a powerful and intelligent solution for splitting large, multi-page PDF documents into individual, logically separated files. It uses the Google Gemini AI model to analyze the content of each page and determine the boundaries of different documents within a single PDF file.

The application is architected as a Python Flask API that can process entire folders of PDFs, making it easy to integrate into larger workflows.

## Architecture

The system is designed with a clean separation of concerns:

-   **`main_api.py`**: This is the front-facing web server built with Flask. It exposes the API endpoints, handles incoming requests, validates input, and manages the subprocess for processing.
-   **`pdf_splitter.py`**: This is the core processing engine. It contains all the logic for PDF analysis, interaction with the Gemini API, and file splitting. It is designed to be run as a standalone script via a subprocess, ensuring that heavy AI processing does not block the API server.

The API (`main_api.py`) communicates with the processing engine (`pdf_splitter.py`) by creating a temporary JSON file with the request details and invoking the script in a new process. The script then writes its output to a uniquely named JSON file, which the API reads and returns to the client.

## Features

-   **Intelligent Document Splitting**: Leverages Google Gemini to understand the content and context of each page.
-   **RESTful API**: Simple `POST` endpoint to process a folder of documents.
-   **Subprocess Architecture**: Ensures the API remains responsive during heavy processing tasks.
-   **MongoDB Integration**: Tracks Gemini API token usage (input, output, and total) for each processing job.
-   **Handles Mixed Content**: Correctly processes multi-page PDFs while identifying and skipping single-page PDFs and images (but still including them in the final report).
-   **Detailed JSON Output**: Provides a clean, structured JSON response with file paths, page counts, and token usage.

## Prerequisites

-   Python 3.8+
-   A running MongoDB instance
-   A Google Gemini API Key

## Setup & Installation

1.  **Clone the repository:**
    ```bash
    git clone <your-repository-url>
    cd document-splitter
    ```

2.  **Install the required Python packages:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Create an environment file:**
    Create a file named `.env` in the root of the project directory. This file will hold your secret keys and database configuration.

## Environment Variables

Your `.env` file must contain the following variables.

```ini
# Your Google Gemini API Key
GEMINI_API_KEY="your-gemini-api-key-here"

# Your MongoDB connection string
MONGO_URI="mongodb://localhost:27017/"

# The name of the MongoDB database to use
MONGO_DB="document_splitter"

# The name of the collection for storing token usage
MONGO_COLLECTION="token_usage"
```

## How to Run the API Server

Once your `.env` file is configured, you can start the Flask API server:

```bash
python main_api.py
```

The API will be available at `http://0.0.0.0:5000`.

## API Usage

### Process a Folder

-   **Endpoint**: `/process`
-   **Method**: `POST`
-   **Description**: Processes all valid files in the specified folder path.

#### Request Body

The request must be a JSON object containing the absolute path to the folder you want to process.

```json
{
    "folder_path": "D:\\path\\to\\your\\documents"
}
```

#### Success Response (`200 OK`)

If successful, the API returns a JSON object with the status, a list of all output files (both split and skipped), and the token usage for the transaction.

```json
{
    "status": "success",
    "status_code": "200",
    "output_files": [
        {
            "original_file_path": "D:\\AIQoD\\Projects\\document-splitter\\solo_test2\\Aditya_BGV Doc_250617_163101.pdf",
            "path": "D:\\AIQoD\\Projects\\document-splitter\\solo_test2\\Aditya_BGV Doc_250617_163101_list-of-acceptable-documents_1.pdf",
            "is_multipage": false
        },
        {
            "original_file_path": "D:\\AIQoD\\Projects\\document-splitter\\solo_test2\\Aditya_BGV Doc_250617_163101.pdf",
            "path": "D:\\AIQoD\\Projects\\document-splitter\\solo_test2\\Aditya_BGV Doc_250617_163101_employment-verification-form_2-3-4-5.pdf",
            "is_multipage": true,
            "start_page": 2,
            "end_page": 5
        },
        {
            "original_file_path": "D:\\AIQoD\\Projects\\document-splitter\\solo_test2\\Aditya_BGV Doc_250617_163101.pdf",
            "path": "D:\\AIQoD\\Projects\\document-splitter\\solo_test2\\Aditya_BGV Doc_250617_163101_employment-screening-consent_6.pdf",
            "is_multipage": false
        },
        // ... more output files ...
    ],
    "input_tokens": 5980,
    "output_tokens": 1216,
    "total_tokens": 10449
}
```

#### Error Response

If an error occurs (e.g., folder not found, processing failure), the API will return a JSON object with an error message.

```json
{
    "status": "error",
    "status_code": "400",
    "error": "Folder path does not exist: D:\\path\\to\\non_existent_folder"
}
```

---

### Cut a PDF by Page Numbers

-   **Endpoint**: `/cut_pdf`
-   **Method**: `POST`
-   **Description**: Cuts a PDF file in the specified folder from a given start page to an end page and returns the new file path. This is a direct, page-range-based cut (no AI analysis or document classification).

#### Request Body

The request must be a JSON object containing:

-   `folder_path`: The absolute path to the folder containing the PDF(s).
-   `start_page`: The starting page number (1-indexed).
-   `end_page`: The ending page number (1-indexed).

Example:

```json
{
    "folder_path": "D:\\path\\to\\your\\documents",
    "start_page": 1,
    "end_page": 5
}
```

#### Success Response (`200 OK`)

If successful, the API returns a JSON object with the status and the path to the new cut PDF file. Token counts are always zero for this endpoint, as no AI analysis is performed.

```json
{
    "status": "success",
    "status_code": "200",
    "output_files": [
        {
            "path": "D:\\path\\to\\your\\documents\\document_1_aadhar-card_7.pdf"
        }
    ],
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0
}
```

#### Error Response

If an error occurs (e.g., folder not found, invalid page range), the API will return a JSON object with an error message.

```json
{
    "status": "error",
    "status_code": "400",
    "error": "No PDF files found in the specified folder"
}
```

---

### Endpoint Comparison

-   **`/process`**: Uses Gemini AI to analyze and split all PDFs in a folder into logical documents, returning detailed file info and token usage.
-   **`/cut_pdf`**: Directly cuts a single PDF by page range (no AI), returning the new file path. Token usage is always zero for this endpoint.