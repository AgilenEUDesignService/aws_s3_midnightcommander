import json

def copy_json_to_clipboard(root,data):
    """
    Copy Python data as formatted JSON to clipboard.
    """
    text=json.dumps(data,indent=2)
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update() # ensure clipboard persistence
