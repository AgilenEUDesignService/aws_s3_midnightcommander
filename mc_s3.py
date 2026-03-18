import os
import time
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from datetime import datetime, timezone
import webbrowser
import shutil

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from boto3.s3.transfer import TransferConfig # parallel downloads

from transfer_manager_addon import TransferManager
from config_manager_addon import ConfigManager

# ---------- AWS session helper ----------
def make_session(profile_name=None, region_name=None):
    if profile_name:
        return boto3.Session(profile_name=profile_name, region_name=region_name)
    return boto3.Session(region_name=region_name)

# ---------- Local FS util ----------
def list_local_dir(path):
    entries = []
    with os.scandir(path) as it:
        for e in it:
            try:
                is_dir = e.is_dir(follow_symlinks=True)
                st = e.stat(follow_symlinks=True)
                entries.append({
                    "name": e.name,
                    "is_dir": is_dir,
                    "size": None if is_dir else st.st_size,
                    "mtime": datetime.fromtimestamp(st.st_mtime),
                })
            except Exception:
                # Skip entries we cannot stat
                continue
    entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
    return entries

# ---------- Simple selection dialog ----------
class SelectionDialog(tk.Toplevel):
    def __init__(self, parent, title, prompt, items, display_attr=None, width=480, height=360):
        super().__init__(parent)
        self.title(title)
        self.resizable(True, True)
        self.result = None
        self.geometry(f"{width}x{height}")
        self.transient(parent)
        self.grab_set()

        frm = ttk.Frame(self, padding=8)
        frm.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frm, text=prompt).pack(anchor="w", pady=(0,6))
        self.listbox = tk.Listbox(frm, selectmode=tk.SINGLE)
        self.listbox.pack(fill=tk.BOTH, expand=True)
        self.items = items
        self.display_attr = display_attr
        for i, it in enumerate(items):
            if display_attr:
                self.listbox.insert(tk.END, getattr(it, display_attr, str(it)) if not isinstance(it, dict) else it.get(display_attr, str(it)))
            else:
                self.listbox.insert(tk.END, str(it))
        btns = ttk.Frame(frm)
        btns.pack(fill=tk.X, pady=(8,0))
        ttk.Button(btns, text="OK", command=self.on_ok).pack(side=tk.RIGHT)
        ttk.Button(btns, text="Cancel", command=self.on_cancel).pack(side=tk.RIGHT, padx=(0,8))
        self.bind("<Return>", lambda e: self.on_ok())
        self.bind("<Escape>", lambda e: self.on_cancel())
        self.listbox.focus_set()

    def on_ok(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        self.result = self.items[idx]
        self.destroy()

    def on_cancel(self):
        self.result = None
        self.destroy()

# ---------- App ----------
class DualPaneS3(tk.Tk):
    def __init__(self):
        super().__init__()


        self.config = ConfigManager()

        # --- Aply clam theme ---
        style = ttk.Style()
        style.theme_use("clam")

        style.configure('TreeView',
                        background="#f5f5f5",
                        foreground="black",
                        fieldbackground="#f5f5f5",
                        rowheight=22)
        style.configure("Treeview.Heading",
                        background="#dddddd",
                        foreground="black")
        style.map('Treeview',
                  background=[('selected', '#0078d4')],
                  foreground=[('selected', 'white')])

        style.configure('TButton',padding=4)
        style.configure('TLabel', padding=2)
        style.configure('TEntry', padding=2)




        self.title("Midnight Commander–style S3 Manager (Pure boto3 SSO)")
        self.geometry("1280x720")
        self.minsize(980, 600)

        # SSO runtime state
        self._sso_state = None  # dict with: session, expiration_ms, account_id, role_name, sso_region

        #Enable S3-validated checksums
        self.checksum_algo ="SHA256"
        #self.checksum_algo ="CRC64_NVME"

        #Large transfer config
        #self.transfer_config = TransferConfig(
        #        multipart_threshold = 8 * 1024 * 1024 , # 8 MB
        #        max_concurrency = 8 ,                   # 8 paralles threads
        #        multipart_chunksize = 8 * 1024 * 1024,  # * MB chunks
        #        use_threads=True
        #        )


        self._build_ui()
        self._bind_keys()
        self.transfer_manager = TransferManager(self)

        # Restore config values
        self.profile_var.set(self.config.get("profile"))
        self.region_var.set(self.config.get("region"))
        self.bucket_var.set(self.config.get("bucket"))
        self.prefix_var.set(self.config.get("prefix"))
        self.local_path_var.set(self.config.get("local_path"))
        self.transfer_mode_var.set(self.config.get("transfer_mode"))
        self.sso_start_url_var.set(self.config.get("sso_start_url"))
        self.sso_region_var.set(self.config.get("sso_region"))
        
        # Restore window geometry
        geom = self.config.get("geometry")
        if geom:
            try:
                self.geometry(geom)
            except:
                pass


        # Set transferconfig
        self.transfer_mode_var = tk.StringVar(value="High-Speed")
        self.update_transfer_config()

        # init state
        #self.local_path_var.set(os.path.expanduser("~"))
        self.local_path_var.set(self.config.get("local_path"))
        self.refresh_local()

    # ---------- UI ----------
    def _build_ui(self):
        # Toolbar
        toolbar = ttk.Frame(self, padding=8)
        toolbar.pack(side=tk.TOP, fill=tk.X)

        self.profile_var = tk.StringVar()
        self.region_var = tk.StringVar()
        self.region_var.trace_add("write", lambda *args:
                                  self.config.set("region", self.region_var.get()))
        self.recursive_var = tk.BooleanVar(value=True)

        ttk.Label(toolbar, text="AWS Profile:").pack(side=tk.LEFT, padx=(0,4))
        self.profile_cb = ttk.Combobox(toolbar, textvariable=self.profile_var, width=16)
        self.profile_cb["values"] = self._detect_profiles()
        self.profile_cb.pack(side=tk.LEFT, padx=(0,10))
        self.profile_cb.bind("<<ComboboxSelected>>", lambda e:
                             self.config.set("profile",self.profile_var.get()))


        ttk.Label(toolbar, text="Region:").pack(side=tk.LEFT, padx=(0,4))
        ttk.Entry(toolbar, textvariable=self.region_var, width=14).pack(side=tk.LEFT, padx=(0,10))

        ttk.Button(toolbar, text="Load Buckets", command=self.load_buckets).pack(side=tk.LEFT, padx=(0,10))
        ttk.Checkbutton(toolbar, text="S3 Recursive", variable=self.recursive_var).pack(side=tk.LEFT)

        # SSO controls (pure boto flow)
        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(side=tk.LEFT, padx=10, fill=tk.Y)
        ttk.Label(toolbar, text="SSO Start URL:").pack(side=tk.LEFT, padx=(0,4))
        self.sso_start_url_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.sso_start_url_var, width=28).pack(side=tk.LEFT, padx=(0,10))
        self.sso_start_url_var.trace_add("write", lambda *a:
                                         self.config.set("sso_start_url",self.sso_start_url_var.get()))
        ttk.Label(toolbar, text="SSO Region:").pack(side=tk.LEFT, padx=(0,4))
        self.sso_region_var = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.sso_region_var, width=14).pack(side=tk.LEFT, padx=(0,10))
        self.sso_region_var.trace_add("write", lambda *a:
                                      self.config.set("sso_region",self.sso_region_var.get()))
        ttk.Button(toolbar, text="SSO Login & Select Role", command=self.sso_login_and_select).pack(side=tk.LEFT)

        # --- Transfer Mode Selection ---
        ttk.Label(toolbar, text = "Transfer Mode:").pack(side=tk.LEFT,padx=(12,4))

        self.transfer_mode_var= tk.StringVar(value="High-Speed")
        self.transfer_mode_cb = ttk.Combobox(
                toolbar,
                textvariable=self.transfer_mode_var,
                values = ["Balanced", "High-Speed", "Low-Resource"],
                width=14,
                state="readonly"
                )
        self.transfer_mode_cb.pack(side=tk.LEFT,padx=(0,10))

        self.transfer_mode_cb.set(self.transfer_mode_var.get())

        # Update config when changed
        self.transfer_mode_cb.bind("<<ComboboxSelected>>", lambda e: self.update_transfer_config())


        # Panes
        panes = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        panes.pack(fill=tk.BOTH, expand=True)

        # Left: Local
        left = ttk.Labelframe(panes, text="Local", padding=6)
        panes.add(left, weight=1)

        local_top = ttk.Frame(left)
        local_top.pack(side=tk.TOP, fill=tk.X, pady=(0,4))
        self.local_path_var = tk.StringVar()
        ttk.Entry(local_top, textvariable=self.local_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(local_top, text="Browse…", command=self.pick_local_root).pack(side=tk.LEFT, padx=(6,0))
        ttk.Button(local_top, text="Refresh", command=self.refresh_local).pack(side=tk.LEFT, padx=(6,0))

        self.local_tree = ttk.Treeview(left, columns=("name","size","mtime"), show="headings", selectmode="browse")
        for col, txt, w, anchor in [
            ("name","Name", 580, "w"), ("size","Size", 110, "e"), ("mtime","Modified", 180, "center")
        ]:
            self.local_tree.heading(col, text=txt)
            self.local_tree.column(col, width=w, anchor=anchor)
        l_vsb = ttk.Scrollbar(left, orient="vertical", command=self.local_tree.yview)
        self.local_tree.configure(yscroll=l_vsb.set)
        self.local_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        l_vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.local_tree.bind("<Double-1>", self.on_local_open)

        # Right: S3
        right = ttk.Labelframe(panes, text="S3", padding=6)
        panes.add(right, weight=1)

        s3_top = ttk.Frame(right)
        s3_top.pack(side=tk.TOP, fill=tk.X, pady=(0,4))
        ttk.Label(s3_top, text="Bucket:").pack(side=tk.LEFT)
        self.bucket_var = tk.StringVar()
        self.bucket_cb = ttk.Combobox(s3_top, textvariable=self.bucket_var, width=40)
        self.bucket_cb.pack(side=tk.LEFT, padx=(6,10))
        self.bucket_cb.bind("<<ComboboxSelected>>", lambda e:
                            self.config.set("bucket", self.bucket_var.get()))
        ttk.Button(s3_top, text="Open", command=self.refresh_s3).pack(side=tk.LEFT, padx=(0,6))

        ttk.Label(s3_top, text="Prefix:").pack(side=tk.LEFT)
        self.prefix_var = tk.StringVar()
        ttk.Entry(s3_top, textvariable=self.prefix_var, width=40).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(6,0))
        self.prefix_var.trace_add("write", lambda *a:
                                  self.config.set("prefix",self.prefix_var.get()))
        ttk.Button(s3_top, text="Up", command=self.s3_up).pack(side=tk.LEFT, padx=(6,0))

        self.s3_tree = ttk.Treeview(right, columns=("key","size_mb","last_modified"), show="headings", selectmode="browse")
        for col, txt, w, anchor in [
            ("key","Key / Prefix", 580, "w"), ("size_mb","Size (MB)", 110, "e"), ("last_modified","Last Modified", 180, "center")
        ]:
            self.s3_tree.heading(col, text=txt)
            self.s3_tree.column(col, width=w, anchor=anchor)
        r_vsb = ttk.Scrollbar(right, orient="vertical", command=self.s3_tree.yview)
        self.s3_tree.configure(yscroll=r_vsb.set)
        self.s3_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        r_vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self.s3_tree.bind("<Double-1>", self.on_s3_open)

        # Bottom actions
        actions = ttk.Frame(self, padding=6)
        actions.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(actions, text="F5 Copy → (Upload)", command=self.upload_from_local).pack(side=tk.LEFT)
        ttk.Button(actions, text="F6 Copy ← (Download)", command=self.download_from_s3).pack(side=tk.LEFT, padx=(8,0))
        ttk.Button(actions, text="F7 New Folder", command=self.new_folder).pack(side=tk.LEFT, padx=(8,0))
        ttk.Button(actions, text="Delete", command=self.delete_selected).pack(side=tk.LEFT, padx=(8,0))

        # Status bar
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(self, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w").pack(side=tk.BOTTOM, fill=tk.X)

    def _bind_keys(self):
        self.bind("<F5>", lambda e: self.upload_from_local())
        self.bind("<F6>", lambda e: self.download_from_s3())
        self.bind("<F7>", lambda e: self.new_folder())
        self.bind("<Delete>", lambda e: self.delete_selected())

    # ---------- Helpers ----------
    def _detect_profiles(self):
        try:
            import botocore
            return botocore.session.Session().available_profiles or []
        except Exception:
            return []

    def set_status(self, txt):
        self.status_var.set(txt)
        self.update_idletasks()

    def compute_relative_path(self, key: str) -> str:
        """
        Computes the relative local path for a given S3 key inside a prefix.

        If relative path becomes empty (""), fall back to using the last
        component of the prefix as the folder name.
        """
        prefix = self.prefix_var.get().strip()

        # Normalize prefix
        if prefix and not prefix.endswith("/"):
            prefix = prefix + "/"

        # Case 1: key starts with prefix → strip it
        if prefix and key.startswith(prefix):
            rel = key[len(prefix):]
        else:
            # fallback (should rarely happen)
            rel = key

        # Case 2: rel becomes empty → use last part of prefix
        if rel == "":
            # Extract "trip" from "photos/2024/trip/"
            last = prefix.strip("/").split("/")[-1]
            rel = last + "/"   # ensure folder is created

        return rel

    def update_transfer_config(self):
        """
        Updates self.transfer_config according to the selected mode.
        """
        mode = self.transfer_mode_var.get()

        if mode == "Balanced":
            cfg = TransferConfig(
                    multipart_threshold= 8 * 1024 * 1024,
                    max_concurrency=8,
                    multipart_chunksize=8 * 1024 * 1024,
                    use_threads=True
                    )
        elif mode == "High-Speed":
            cfg = TransferConfig(
                    multipart_threshold= 16 * 1024 * 1024,
                    max_concurrency=16,
                    multipart_chunksize=16 * 1024 * 1024,
                    use_threads=True
                    )
        else:
            # Fallback safest choice
            cfg = TransferConfig(
                    use_threads=True
                    )
        self.transfer_config = cfg
        self.set_status(f"Transfer mode set to:{mode}")

    def on_close(self):
        try:
            self.config.set("geometry",self.geometry())
        except:
            pass
        self.destroy()



    # ---------- SSO (pure boto) ----------
    def sso_login_and_select(self):
        start_url = (self.sso_start_url_var.get() or '').strip()
        sso_region = (self.sso_region_var.get() or '').strip()
        if not start_url or not sso_region:
            messagebox.showwarning("SSO", "Please fill SSO Start URL and SSO Region.")
            return
        def _sso_flow():
            try:
                self.set_status("Starting SSO device authorization…")
                oidc = boto3.client("sso-oidc", region_name=sso_region)
                reg = oidc.register_client(clientName="mc-s3-manager", clientType="public")
                client_id = reg["clientId"]
                client_secret = reg["clientSecret"]

                device = oidc.start_device_authorization(
                    clientId=client_id,
                    clientSecret=client_secret,
                    startUrl=start_url,
                )
                url = device.get("verificationUriComplete") or device["verificationUri"]
                code = device.get("userCode")
                expires_in = int(device["expiresIn"])
                interval = int(device["interval"]) if "interval" in device else 5
                #DEBUG
                print(f"Device,{device}")
                self.set_status(f"Device code: {code}")
                #TODO -> Here have a popup window showing the device code!

                # Open browser
                try:
                    webbrowser.open(url)
                except Exception:
                    pass
                self.set_status(f"Please complete SSO in your browser Device Code:{code}")

                # Poll for token
                access_token = None
                deadline = time.time() + expires_in
                while time.time() < deadline:
                    try:
                        tok = oidc.create_token(
                            clientId=client_id,
                            clientSecret=client_secret,
                            grantType="urn:ietf:params:oauth:grant-type:device_code",
                            deviceCode=device["deviceCode"],
                        )
                        access_token = tok["accessToken"]
                        break
                    except ClientError as e:
                        code_ = e.response.get("Error", {}).get("Code", "").lower()
                        if code_ in ("authorizationpendingexception", "slowdownexception"):
                            time.sleep(interval)
                            continue
                        elif "expired" in code_:
                            raise RuntimeError("Device authorization expired. Restart login.") from e
                        else:
                            raise

                if not access_token:
                    raise RuntimeError("SSO login not completed before expiration.")
                #DEBUG
                print("==================")
                print(f"TOK access token {tok}")
                print("-------------")

                # List accounts and choose
                sso = boto3.client("sso", region_name=sso_region)
                accounts = []
                next_token = None
                while True:
                    kw = {"accessToken": access_token}
                    if next_token:
                        kw["nextToken"] = next_token
                    resp = sso.list_accounts(**kw)
                    accounts.extend(resp.get("accountList", []))
                    next_token = resp.get("nextToken")
                    if not next_token:
                        break
                if not accounts:
                    raise RuntimeError("No SSO accounts found for this user.")

                # Show selection dialog
                nice_accounts = [f"{a['accountName']} ({a['accountId']})" for a in accounts]
                dlg = SelectionDialog(self, "Select SSO Account", "Choose an AWS account:", nice_accounts)
                self.wait_window(dlg)
                if not dlg.result:
                    self.set_status("SSO canceled.")
                    return
                idx = nice_accounts.index(dlg.result)
                account = accounts[idx]
                account_id = account["accountId"]
                #DEBUG
                print("==============")
                print(f"Account: {account}")
                print("--------------")

                # List roles for account
                roles = []
                next_token = None
                while True:
                    kw = {"accessToken": access_token, "accountId": account_id}
                    if next_token:
                        kw["nextToken"] = next_token
                    resp = sso.list_account_roles(**kw)
                    roles.extend(resp.get("roleList", []))
                    next_token = resp.get("nextToken")
                    if not next_token:
                        break
                if not roles:
                    raise RuntimeError("No roles available in the selected account.")

                nice_roles = [r["roleName"] for r in roles]
                dlg2 = SelectionDialog(self, "Select Role", f"Choose a role for account {account_id}:", nice_roles)
                self.wait_window(dlg2)
                if not dlg2.result:
                    self.set_status("SSO canceled.")
                    return
                role_name = dlg2.result

                # Get role credentials
                creds = sso.get_role_credentials(
                    accountId=account_id,
                    roleName=role_name,
                    accessToken=access_token,
                )["roleCredentials"]
                #DEBUG
                print("==========")
                print(f"Role Credentials {creds}")

                region = (self.region_var.get() or '').strip() or sso_region
                session = boto3.Session(
                    aws_access_key_id=creds["accessKeyId"],
                    aws_secret_access_key=creds["secretAccessKey"],
                    aws_session_token=creds["sessionToken"],
                    region_name=region,
                )

                self._sso_state = {
                    "session": session,
                    "expiration_ms": int(creds["expiration"]),
                    "account_id": account_id,
                    "role_name": role_name,
                    "sso_region": sso_region,
                }
                exp = datetime.fromtimestamp(creds["expiration"]/1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
                self.set_status(f"SSO session established (expires {exp}).")
                #TODO add this to a log visible
            except Exception as e:
                messagebox.showerror("SSO Error", str(e))
                self.set_status("SSO failed.")
        threading.Thread(target=_sso_flow, daemon=True).start()

    def _sso_client_if_valid(self, service_name):
        if not self._sso_state:
            return None
        exp_ms = self._sso_state.get("expiration_ms", 0)
        now_ms = int(time.time() * 1000)
        if now_ms + 60_000 >= exp_ms:  # 60s skew
            # expired
            self._sso_state = None
            return None
        sess = self._sso_state.get("session")
        if not sess:
            return None
        return sess.client(service_name)

    def _get_s3_client(self):
        # Prefer valid SSO session if present
        client = self._sso_client_if_valid("s3")
        if client:
            return client

        profile = (self.profile_var.get() or "").strip() or None
        region = (self.region_var.get() or "").strip() or None

        # Try profile/ambient creds
        try:
            return make_session(profile, region).client("s3")
        except Exception as e:
            # If SSO config present, offer to run SSO flow
            start_url = (self.sso_start_url_var.get() or '').strip()
            sso_region = (self.sso_region_var.get() or '').strip()
            if start_url and sso_region:
                if messagebox.askyesno("AWS SSO", "Credentials unavailable. Run SSO login now?"):
                    self.sso_login_and_select()
                    # After login completes, user can retry the action
                    raise RuntimeError("SSO login triggered. Retry your action after login completes.")
            # Otherwise, bubble the error
            raise

    # ---------- Local pane ops ----------
    def pick_local_root(self):
        path = filedialog.askdirectory(initialdir=self.local_path_var.get())
        if path:
            self.local_path_var.set(path)
            self.config.set("local_path",path)
            self.refresh_local()

    def refresh_local(self):
        path = self.local_path_var.get()
        if not path:
            return
        try:
            self.set_status(f"Loading local: {path}")
            for i in self.local_tree.get_children():
                self.local_tree.delete(i)
            # add parent dir pseudo entry
            parent = os.path.dirname(path.rstrip(os.sep)) if path != os.path.dirname(path.rstrip(os.sep)) else None
            if parent:
                self.local_tree.insert("", "end", values=("[..]", "", ""), iid="__PARENT__")
            for e in list_local_dir(path):
                size = "" if e["is_dir"] else f"{e['size']:,}"
                mtime = e["mtime"].strftime("%Y-%m-%d %H:%M:%S")
                disp = f"[{e['name']}]" if e["is_dir"] else e["name"]
                self.local_tree.insert("", "end", values=(disp, size, mtime), iid=e["name"])
            self.set_status("Ready.")
        except Exception as e:
            messagebox.showerror("Local Error", str(e))
            self.set_status("Local load failed.")

    def on_local_open(self, _event=None):
        item = self.local_tree.focus()
        if not item:
            return
        if item == "__PARENT__":
            self.local_path_var.set(os.path.dirname(self.local_path_var.get().rstrip(os.sep)))
            self.config.set("local_path",self.local_path_var.get())
            self.refresh_local()
            return
        name = item
        full = os.path.join(self.local_path_var.get(), name)
        if os.path.isdir(full):
            self.local_path_var.set(full)
            self.config.set("local_path",full)
            self.refresh_local()

    def get_selected_local_path(self):
        item = self.local_tree.focus()
        if not item or item == "__PARENT__":
            return None
        return os.path.join(self.local_path_var.get(), item)

    # ---------- S3 pane ops ----------
    def load_buckets(self):
        def _load():
            try:
                self.set_status("Loading buckets…")
                client = self._get_s3_client()
                resp = client.list_buckets()
                #DEBUG
                print("=========")
                print(f"Response list buckets:")
                print(f"{resp}")
                print("---------")
                names = sorted([b["Name"] for b in resp.get("Buckets", [])])
                self.bucket_cb["values"] = names
                if names and not self.bucket_var.get():
                    self.bucket_var.set(names[0])
                self.set_status(f"Loaded {len(names)} bucket(s).")
            except Exception as e:
                messagebox.showerror("S3 Error", f"Failed to load buckets:\n{e}")
                self.set_status("Error loading buckets.")
        threading.Thread(target=_load, daemon=True).start()

    def refresh_s3(self):
        def _list():
            bucket = (self.bucket_var.get() or "").strip()
            prefix = (self.prefix_var.get() or "").strip()
            if not bucket:
                messagebox.showwarning("Bucket required", "Select a bucket first.")
                return
            self.set_status(f"Listing s3://{bucket}/{prefix}")
            for i in self.s3_tree.get_children():
                self.s3_tree.delete(i)
            try:
                client = self._get_s3_client()
                paginator = client.get_paginator("list_objects_v2")
                params = {"Bucket": bucket}
                if prefix:
                    params["Prefix"] = prefix
                if not self.recursive_var.get():
                    params["Delimiter"] = "/"

                total = 0
                for page in paginator.paginate(**params):
                    for cp in page.get("CommonPrefixes", []):
                        pfx = cp.get("Prefix", "")
                        disp = f"[{pfx}]"
                        self.s3_tree.insert("", "end", values=(disp, "", ""), iid=f"p::{pfx}")
                        total += 1
                    for obj in page.get("Contents", []):
                        key = obj["Key"]
                        size_mb = f"{(obj.get('Size', 0)/(1024*1024)):.3f}"
                        lm = obj.get("LastModified")
                        lm_str = lm.strftime("%Y-%m-%d %H:%M:%S") if isinstance(lm, datetime) else ""
                        self.s3_tree.insert("", "end", values=(key, size_mb, lm_str), iid=f"o::{key}")
                        total += 1
                self.set_status(f"Done. {total} item(s).")
            except Exception as e:
                messagebox.showerror("S3 Error", f"Failed to list objects:\n{e}")
                self.set_status("Error listing S3.")
        threading.Thread(target=_list, daemon=True).start()

    def s3_up(self):
        prefix = (self.prefix_var.get() or "").strip()
        if not prefix:
            return
        p = prefix[:-1] if prefix.endswith("/") else prefix
        if "/" in p:
            new_pfx = p.rsplit("/", 1)[0] + "/"
        else:
            new_pfx = ""
        self.prefix_var.set(new_pfx)
        self.refresh_s3()

    def on_s3_open(self, _event=None):
        item = self.s3_tree.focus()
        if not item:
            return
        if item.startswith("p::"):
            pfx = item.split("::",1)[1]
            self.prefix_var.set(pfx)
            self.refresh_s3()

    def get_selected_s3(self):
        item = self.s3_tree.focus()
        if not item:
            return None, None
        if item.startswith("p::"):
            return "prefix", item.split("::",1)[1]
        elif item.startswith("o::"):
            return "object", item.split("::",1)[1]
        return None, None

    # ---------- Transfers ----------
    def upload_from_local(self):
        local_path = self.get_selected_local_path()
        bucket = (self.bucket_var.get() or "").strip()
        base_prefix = (self.prefix_var.get() or "").strip()
        if not local_path:
            messagebox.showinfo("Upload", "Select a local file or folder to upload.")
            return
        if not bucket:
            messagebox.showwarning("Bucket required", "Select a bucket.")
            return
        if os.path.isdir(local_path):
            target = simpledialog.askstring("Upload folder", "Upload folder under prefix (e.g. data/project/):",
                                            initialvalue=base_prefix)
            if target is None:
                return
            def _upload_dir():
                try:
                    self.set_status("Uploading folder…")
                    client = self._get_s3_client()
                    for root, dirs, files in os.walk(local_path):
                        for f in files:
                            full = os.path.join(root, f)
                            rel = os.path.relpath(full, local_path).replace("\\","/")
                            key = (target + rel) if target.endswith("/") else (target + "/" + rel if target else rel)
                            extra_args={}
                            if self.checksum_algo:
                                extra_args["ChecksumAlgorithm"]=self.checksum_algo

                            #client.upload_file(full, bucket, key,ExtraArgs=extra_args, Config=self.transfer_config)
                            #Call back with Transfer manager
                            callback=self.transfer_manager.create_callback(f,os.path.getsize(full))
                            client.upload_file(full, bucket, key,ExtraArgs=extra_args, Config=self.transfer_config, Callback=callback)
                            self.transfer_manager.mark_done(callback.transfer_id)
                            
                    self.set_status("Folder upload complete.")
                    self.refresh_s3()
                except Exception as e:
                    messagebox.showerror("Upload Error", str(e))
                    self.set_status("Upload failed.")
            threading.Thread(target=_upload_dir, daemon=True).start()
            return

        key_default = (base_prefix if base_prefix.endswith("/") or base_prefix == "" else base_prefix + "/") + os.path.basename(local_path)
        key = simpledialog.askstring("Upload file", "S3 key:", initialvalue=key_default)
        if not key:
            return

        # PATCHED below

        def _upload():
            try:
                self.set_status(f"Uploading {os.path.basename(local_path)} → s3://{bucket}/{key}")
                client = self._get_s3_client()

                extra_args = {}
                if self.checksum_algo:
                    extra_args["ChecksumAlgorithm"] = self.checksum_algo  # Option A: backend-validated checksum
                print("Extra arguments:",extra_args)

                #client.upload_file(local_path, bucket, key, ExtraArgs=extra_args, Config=self.transfer_config)
                #Add call back
                callback= self.transfer_manager.create_callback(os.path.basename(local_path),os.path.getsize(local_path))

                client.upload_file(local_path, bucket, key, ExtraArgs=extra_args, Config=self.transfer_config, Callback=callback)
                self.transfer_manager.mark_done(callback.transfer_id)

                self.set_status("Upload complete.")
                self.refresh_s3()
            except Exception as e:
                messagebox.showerror("Upload Error", str(e))
                self.set_status("Upload failed.")
        threading.Thread(target=_upload, daemon=True).start()

    #FIX 1 DEBUG
#    def compute_relative_path(self,key: str) -> str:
#        """
#        Computes the relative local path for a given S3 key inside a prefix.
#
#        If relative path becomes empty (""), fall back to using the last
#        component of the prefix as the folder name.
#        """
#        prefix = self.prefix_var.get().strip()
#        # Normalize prefix
#        if prefix and not prefix.endswith("/"):
#            prefix = prefix + "/"
#
#        # Case 1: key starts with prefix → strip it
#        if prefix and key.startswith(prefix):
#            rel = key[len(prefix):]
#        else:
#            # fallback (should rarely happen)
#            rel = key
#
#        # Case 2: rel becomes empty → use last part of prefix
#        if rel == "":
#            # Extract "trip" from "photos/2024/trip/"
#            last = prefix.strip("/").split("/")[-1]
#            rel = last + "/"   # ensure folder is created
#
#        return rel


    def download_from_s3(self):
        typ, sel = self.get_selected_s3()
        if not sel:
            messagebox.showinfo("Download", "Select an S3 object or prefix to download.")
            return
        if typ == "prefix":
            #local_dir = filedialog.askdirectory(initialdir=self.local_path_var.get(), title="Download to directory")
            local_dir =self.local_path_var.get().strip() # Download directly to left pane
            if not local_dir:
                return
            bucket = self.bucket_var.get().strip()
            prefix = sel
            def _dl_prefix():
                #TODO fix here!!!!! it doesn't download folders properly
                try:
                    self.set_status(f"Downloading s3://{bucket}/{prefix} → {local_dir}")
                    client = self._get_s3_client()
                    paginator = client.get_paginator("list_objects_v2")
                    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                        for obj in page.get("Contents", []):
                            #DEBUG
                            print(f"Object in prefix: {obj}")
                            print(f"prefix {prefix}")
                            key = obj["Key"]
                            rel = key[len(prefix):] if key.startswith(prefix) else key
                            print(f"LEft rel: {rel}")
                            rel= self.compute_relative_path(key)
                            print(f"LEft rel: {rel}")
                            dest = os.path.join(local_dir, rel)
                            os.makedirs(os.path.dirname(dest), exist_ok=True)
                            if not key.endswith("/"):
                                print(f"Key {key}")
                                #client.download_file(bucket, key, dest,Config=self.transfer_config) #download files skip directories
                                # Downlaod callback to trasnfer manager

                                # Retrieve size
                                obj_head=client.head_object(Bucket=bucket,Key=key)
                                obj_size_bytes =obj_head["ContentLength"]

                                callback = self.transfer_manager.create_callback(os.path.basename(key),obj_size_bytes)
                                client.download_file(bucket, key, dest,Config=self.transfer_config, Callback=callback) #download files skip directories
                                self.transfer_manager.mark_done(callback.transfer_id)
                    self.set_status("Download complete.")
                    self.refresh_local()
                except Exception as e:
                    messagebox.showerror("Download Error", str(e))
                    self.set_status("Download failed.")
            threading.Thread(target=_dl_prefix, daemon=True).start()
        else:
            bucket = self.bucket_var.get().strip()
            key = sel
            #save_as = filedialog.asksaveasfilename(initialdir=self.local_path_var.get(),
            #                                       initialfile=os.path.basename(key))
            save_as=os.path.join(self.local_path_var.get(),os.path.basename(key))
            #DEBUG
            print("==========")
            print(f"save_as: {save_as}")
            print("----------")
            if not save_as:
                return
            def _dl():
                try:
                    self.set_status(f"Downloading s3://{bucket}/{key} → {save_as}")
                    client = self._get_s3_client()
                    os.makedirs(os.path.dirname(save_as), exist_ok=True)
                    #client.download_file(bucket, key, save_as, Config=self.transfer_config)
                    #Download with callback to transfer manager
                    obj =client.head_object(Bucket=bucket, Key=key)
                    obj_size_bytes = obj["ContentLength"]

                    callback=self.transfer_manager.create_callback(os.path.basename(key),obj_size_bytes)
                    client.download_file(bucket, key, save_as, Config=self.transfer_config, Callback=callback)
                    self.transfer_manager.mark_done(callback.transfer_id)
                    self.set_status("Download complete.")
                    self.refresh_local()
                except Exception as e:
                    messagebox.showerror("Download Error", str(e))
                    self.set_status("Download failed.")
            threading.Thread(target=_dl, daemon=True).start()

    # ---------- New folder ----------
    def new_folder(self):
        focus_widget = self.focus_get()
        if focus_widget in (self.local_tree,):
            name = simpledialog.askstring("New local folder", "Folder name:")
            if not name:
                return
            path = os.path.join(self.local_path_var.get(), name)
            try:
                os.makedirs(path, exist_ok=False)
                self.refresh_local()
            except Exception as e:
                messagebox.showerror("Local Error", str(e))
        else:
            bucket = (self.bucket_var.get() or "").strip()
            base = (self.prefix_var.get() or "").strip()
            if not bucket:
                messagebox.showwarning("Bucket required", "Select a bucket first.")
                return
            name = simpledialog.askstring("New S3 folder", "Folder (prefix) name:")
            if not name:
                return
            pfx = (base + name + "/") if not name.endswith("/") else (base + name)
            def _mk():
                try:
                    self.set_status(f"Creating s3://{bucket}/{pfx}")
                    client = self._get_s3_client()
                    client.put_object(Bucket=bucket, Key=pfx)
                    self.set_status("Folder created.")
                    self.refresh_s3()
                except Exception as e:
                    messagebox.showerror("S3 Error", str(e))
                    self.set_status("Create failed.")
            threading.Thread(target=_mk, daemon=True).start()

    # ---------- Delete ----------
    def delete_selected(self):
        fw = self.focus_get()
        if fw == self.local_tree:
            path = self.get_selected_local_path()
            if not path:
                return
            if not messagebox.askyesno("Delete", f"Delete local {'folder' if os.path.isdir(path) else 'file'}?\n{path}"):
                return
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                self.refresh_local()
            except Exception as e:
                messagebox.showerror("Local Delete Error", str(e))
        else:
            typ, sel = self.get_selected_s3()
            if not sel:
                return
            bucket = (self.bucket_var.get() or "").strip()
            if typ == "object":
                if not messagebox.askyesno("Delete", f"Delete S3 object?\ns3://{bucket}/{sel}"):
                    return
                def _del_obj():
                    try:
                        client = self._get_s3_client()
                        client.delete_object(Bucket=bucket, Key=sel)
                        self.refresh_s3()
                    except Exception as e:
                        messagebox.showerror("S3 Delete Error", str(e))
                threading.Thread(target=_del_obj, daemon=True).start()
            else:
                if not messagebox.askyesno("Delete", f"Recursively DELETE all under prefix?\ns3://{bucket}/{sel}"):
                    return
                def _del_pfx():
                    try:
                        client = self._get_s3_client()
                        paginator = client.get_paginator("list_objects_v2")
                        to_delete = []
                        for page in paginator.paginate(Bucket=bucket, Prefix=sel):
                            for obj in page.get("Contents", []):
                                to_delete.append({"Key": obj["Key"]})
                                if len(to_delete) == 1000:
                                    client.delete_objects(Bucket=bucket, Delete={"Objects": to_delete})
                                    to_delete.clear()
                        if to_delete:
                            client.delete_objects(Bucket=bucket, Delete={"Objects": to_delete})
                        self.refresh_s3()
                    except Exception as e:
                        messagebox.showerror("S3 Delete Error", str(e))
                threading.Thread(target=_del_pfx, daemon=True).start()

if __name__ == "__main__":
    app = DualPaneS3()
    app.protocol("WM_DELETE_WINDOW",app.on_close)
    app.mainloop()
