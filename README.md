Music streaming stats
=====================

To run the Spotify script on Windows:

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

py .\spotify-stats.py <input path> <output path>
```

The script writes a set of CSV and JSON files if you pass the `--output-path` parameter.

The script writes data to PostgreSQL if you pass the `--postgresql` parameter. The connection parameters can be set using other parameters but by default match those of the PostgreSQL container that's created by the included `compose.yml`.

It's possible to visualise the data stored in PostgreSQL using Grafana. To set that up:

1. Run `podman compose up` if PostgreSQL and Grafana are not already running
2. Open `http://localhost:3000/` in your web browser
3. Log in using the username `admin` and password `admin`
4. Change the admin password when prompted
5. On the getting started page, select the option to add a data source
6. Select PostgreSQL as the data source to add
7. Set the "Host URL" to `postgres:5432`, the "Database name" to `postgres`, the "Password" to `password` and "TLS/SSL Mode" to `disable`.
8. Click the "Save & test" button at the bottom of the screen - a green box should appear saying that the database connection is OK.
9. Copy the last part of the page's URL path to your clipboard (e.g. if the URL is `http://localhost:3000/connections/datasources/edit/be68m28l3yjuoa`, copy `be68m28l3yjuoa`).
10. Click the + icon in the top right corner of the screen and select the "Import dashboard" button
11. Open the `grafana-dashboard.json` file in this repository in a text editor.
12. Replace all instances of `be68m28l3yjuoa` in the file with the value that you copied.
13. Paste the JSON file content into the large text box on the "Import dashboard" page in your web browser.
14. Click the "Load" button at the bottom of the page.

**The default configuration uses hardcoded plaintext secrets and is not intended for production!**
