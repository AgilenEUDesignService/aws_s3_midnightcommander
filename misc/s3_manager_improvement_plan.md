
# Improvement Plan for Midnight Commander–Style S3 Manager

This document contains structured suggestions for improving Tkinter + boto3 S3 Manager project. In order to track and implement them step-by-step in your Git repository.

---

## ✅ High‑Impact Feature Upgrades

### [X] 1. Parallel Transfer Manager
- Use boto3 TransferConfig for multi-threaded uploads/downloads.
- Faster performance for large files.

### 2. File Transfer Progress Bars
- Implement progress callbacks.
- Show MB/s, ETA, percentage.

### 3. Transfer Queue Window
- Queue operations.
- Show status: pending, running, completed, failed.
- Allow cancellation.

### 4. Persistent User Configuration
- Save selected profile, region, bucket, UI positions.
- Store in JSON/YAML.

### 5. Robust Logging
- Replace print statements with Python logging.
- Log viewer inside the UI.

---

## 🎨 UI/UX Enhancements

### [X] 1. Modern ttk Theme
- Apply clam or a custom theme.

### 2. Improve Keyboard Shortcuts
- Tab to switch pane.
- F3 view, F4 edit, F8 delete.

### 3. Persist Pane Widths
- Store sash positions.

### 4. Drag & Drop Support
- Drag from local to S3 and vice versa using tkinterdnd2.

---

## 🚀 AWS Functional Improvements

### [X] 1. Fix Folder Download Logic
- Remove debug placeholder.
- Correct relative path reconstruction.

### 2. Add S3 Object Metadata Viewer
- Show size, ETag, checksum, encryption, storage class.

### 3. S3 Select Preview
- CSV/JSON preview window.

### 4. Presigned URL Generator
- Right-click → "Copy Presigned URL".

### 5. Glacier Restore Support
- Initiate restore.
- Show status.

---

## 🧹 Code Quality & Architecture

### 1. Separate Logic Into Modules
- app.py (UI)
- s3_client.py
- local_fs.py
- sso_auth.py
- transfer_manager.py

### 2. Use Type Hints
- Improve maintainability.

### 3. Consistent Threading Strategy
- Centralized worker + queue.

### 4. Automatic SSO Token Refresh

---

## 📦 Packaging

- Provide PyInstaller or cx_Freeze builds.
- Optional updater for new releases.

---


