# B2 Client

Small Streamlit client for Backblaze B2 using its S3-compatible API through boto3.

## Windows setup

Unzip/copy this folder to:

```text
C:\b2_client
```

Then:

```powershell
cd C:\b2_client
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Edit `.env` and insert your NEW rotated B2 credentials.

Run:

```powershell
streamlit run app.py
```

Or double-click `start-windows.bat`.

## Linux setup

On Debian or Ubuntu:

```bash
sudo apt update
sudo apt install python3-venv zenity
cd /path/to/b2_client
python3 -m venv .venv-linux
source .venv-linux/bin/activate
pip install -r requirements.txt
./start-linux.sh
```

Linux uses Zenity for native file and folder dialogs. Windows uses Tk dialogs
provided by the standard Windows Python installation. Paths and worker process
checks are selected automatically for the current operating system.

## Mapping

The bucket itself represents Vidos.

Local:
`D:\Vidos\TV_S\Poirot\S01\E01.mkv`

B2 object key:
`TV_S/Poirot/S01/E01.mkv`

## First test

1. Test connection.
2. Upload one small file.
3. Browse it.
4. Download it.
5. Upload one large video.
6. Interrupt and rerun the upload.
7. Verify the folder by size.
8. Only then try a large batch.

Uploads above 64 MiB use boto3 multipart transfer.

## Copy and move inside B2

Use the **Copy / move** tab to copy either one object or an entire folder
prefix without downloading it first. A move copies the data first and only
then deletes the source. For recursive folder moves, source deletion begins
only after every object was copied successfully.

Destination objects are not overwritten unless **Overwrite destination
objects if they already exist** is selected.
