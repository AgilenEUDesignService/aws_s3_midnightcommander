# Midnight Commander–style S3 Manager (Tkinter, Pure boto3 SSO)

A dual‑pane GUI: **left = local filesystem**, **right = Amazon S3**. Includes optional **pure‑Python AWS IAM Identity Center (SSO)** login using `boto3` and the **device code flow** — no AWS CLI required.

## Requirements

- Python 3.8+
- `boto3`
- Tkinter (bundled with most Python installers)

```bash
pip install boto3
```

## Run

```bash
python3 mc_s3.py
```

## SSO (without AWS CLI)
- Fill **SSO Start URL** (e.g. `https://your-domain.awsapps.com/start`) and **SSO Region** (e.g. `eu-west-1`).
- Click **SSO Login & Select Role** → your browser opens.
- After you approve, the app lists your **accounts** and then **roles**. Pick one.
- The app uses the issued **temporary role credentials** to create S3 clients.

> Note: Credentials expire after a while. If they expire, run SSO Login again.

## Features
- Dual‑pane: Local (left) and S3 (right)
- Navigate prefixes; optional delimiter mode
- **F5** Upload (file/folder), **F6** Download (object/prefix), **F7** New folder (prefix), **Delete** (object/prefix or local)
- Background threads for long operations

## Tips
- If you also use non‑SSO profiles, pick a profile and region and click **Load Buckets**. The app will use that profile.
- If profile credentials are missing, and SSO fields are filled, the app can prompt you to login with SSO and then retry.
