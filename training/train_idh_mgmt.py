import os, sys, glob, json, re, time
sys.path.insert(0,"/tmp")
import numpy as np, pandas as pd, nibabel as nib
from radiogenomics import extract_features, FEATURES
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import roc_auc_score
import joblib
SCRATCH="/private/tmp/claude-501/-Users-zeynepersoz-G-NCEL-A---NeuroOncoTrackAI--claude-worktrees-model-quality-xai-improvements-042772/6bcb1e31-f7b9-4b71-bcce-ed929ba0e814/scratchpad"
META="/Users/zeynepersoz/Downloads/UCSF-PDGM-metadata_v5.csv"
ROOT="/Users/zeynepersoz/.cache/kagglehub/datasets/rukiyeaydn/ucsf-pdgm-filtered/versions/1/ucsf"

def idh_bin(v):
    v=str(v).lower()
    if v=="wildtype": return 0
    if "idh" in v or "mutat" in v: return 1
    return np.nan
def mgmt_bin(v):
    v=str(v).lower()
    if v=="positive": return 1
    if v=="negative": return 0
    return np.nan

def realfile(p):
    if os.path.isfile(p): return p
    if os.path.isdir(p):
        inner=os.path.join(p, os.path.basename(p))
        if os.path.isfile(inner): return inner
        fs=glob.glob(os.path.join(p,"*.nii*"))
        return fs[0] if fs else None
    return None

def load_vol(pid):
    m=re.search(r"(\d+)\s*$",pid)
    if not m: return None
    num=int(m.group(1)); base=f"UCSF-PDGM-{num:04d}"
    d=os.path.join(ROOT,base+"_nifti")
    t1c=os.path.join(d,base+"_T1c.nii"); fl=os.path.join(d,base+"_FLAIR.nii"); mk=os.path.join(d,base+"_tumor_segmentation.nii")
    t1c=realfile(t1c); fl=realfile(fl); mk=realfile(mk)
    if not (t1c and mk): return None
    try:
        a=nib.load(t1c); sp=a.header.get_zooms()[:3]; t1=a.get_fdata().astype(np.float32)
        fla=nib.load(fl).get_fdata().astype(np.float32) if fl else t1
        seg=nib.load(mk).get_fdata(); msk=(seg>0)
        if fla.shape!=t1.shape: fla=t1
        if msk.shape!=t1.shape: return None
        return t1,fla,msk,sp
    except Exception: return None

def main():
    df=pd.read_csv(META); df["idh"]=df["IDH"].map(idh_bin); df["mgmt"]=df["MGMT status"].map(mgmt_bin)
    X=[];ids=[];yi=[];ym=[];t0=time.time();miss=0
    for _,r in df.iterrows():
        pid=str(r["ID"]); got=load_vol(pid)
        if got is None: miss+=1; continue
        t1,fla,msk,sp=got
        if msk.sum()<30: miss+=1; continue
        f=extract_features(t1,fla,msk,sp)
        X.append([f[k] for k in FEATURES]); ids.append(pid); yi.append(r["idh"]); ym.append(r["mgmt"])
        if len(X)%25==0: print(f"  {len(X)} işlendi, {miss} eşleşmedi ({time.time()-t0:.0f}s)",flush=True)
    X=np.array(X);yi=np.array(yi);ym=np.array(ym)
    print(f"\nMATRİS {X.shape} | eşleşmeyen {miss}",flush=True)
    np.savez_compressed(SCRATCH+"/radiomics_feats.npz",X=X,ids=np.array(ids),y_idh=yi,y_mgmt=ym)
    def run(name,y):
        mk=~np.isnan(y); Xs=X[mk]; ys=y[mk].astype(int)
        sc=StandardScaler().fit(Xs); Xn=sc.transform(Xs)
        skf=StratifiedKFold(5,shuffle=True,random_state=42); oof=np.zeros(len(ys))
        for tr,te in skf.split(Xn,ys):
            rf=RandomForestClassifier(400,class_weight="balanced",random_state=42,n_jobs=-1).fit(Xn[tr],ys[tr])
            gb=GradientBoostingClassifier(random_state=42).fit(Xn[tr],ys[tr])
            oof[te]=0.6*rf.predict_proba(Xn[te])[:,1]+0.4*gb.predict_proba(Xn[te])[:,1]
        auc=roc_auc_score(ys,oof)
        rf=RandomForestClassifier(400,class_weight="balanced",random_state=42,n_jobs=-1).fit(Xn,ys)
        gb=GradientBoostingClassifier(random_state=42).fit(Xn,ys)
        joblib.dump({"rf":rf,"gb":gb,"scaler":sc,"features":FEATURES,"auc":round(float(auc),3),
                     "n":int(len(ys)),"pos":int(ys.sum())},SCRATCH+f"/model_{name}.pkl")
        print(f">>> {name.upper()}: AUC={auc:.3f}  (pozitif {ys.sum()}/{len(ys)}, 5-fold CV)",flush=True)
        return auc
    run("idh",yi); run("mgmt",ym)
    print("IDH_MGMT_DONE",flush=True)

if __name__=="__main__": main()
