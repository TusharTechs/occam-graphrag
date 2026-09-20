"""Fetch the hackathon corpus and question sets into ./data.

The files are the ones published in the organisers' shared Drive folder; they
are not committed because the corpus is 22 MB of CC BY-SA Wikipedia text.
"""
import pathlib, urllib.request

FILES = {
    "corpus.jsonl":      "1g-XApuwcZfD2tYF6di9QLmFFl_TPe5OO",
    "eval_public.jsonl": "1wpIdvUDOJDfG5c1A_o6IXi_uHpRTY8cG",
    "eval_hidden.jsonl": "1L-3Aum_nZ0FsGwVpWv_IpzREzALYRm2E",
}
BASE = "https://drive.usercontent.google.com/download?id={}&export=download&confirm=t"

def main() -> None:
    out = pathlib.Path(__file__).resolve().parent.parent / "data"
    out.mkdir(exist_ok=True)
    for name, fid in FILES.items():
        dest = out / name
        if dest.exists():
            print(f"  have {name}")
            continue
        print(f"  fetching {name} ...")
        urllib.request.urlretrieve(BASE.format(fid), dest)
    print("done")

if __name__ == "__main__":
    main()
