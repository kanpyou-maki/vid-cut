import { useCallback, useEffect, useState } from "react";
import { useApi } from "../api/ApiContext";
import { errorMessage } from "../api/errors";
import type { FsListing } from "../api/types";

export type Browse =
  | { status: "loading" }
  | { status: "failed"; message: string }
  | { status: "loaded"; listing: FsListing };

/** 開こうとしているフォルダ。同じフォルダでも、頼むたびに作り直して読み直させる。path が null ならホーム */
interface Target {
  path: string | null;
}

const LOADING: Browse = { status: "loading" };

/**
 * 投入ダイアログが見ているフォルダの一覧（`/api/fs`）。
 *
 * open で別のフォルダへ移る（読み取りの途中なら、それを中断する）。
 * onLoaded には読めたフォルダのパスを渡す。呼ぶたびに変わらない関数を渡すこと。
 */
export function useDirectory(
  initialPath: string | null,
  onLoaded: (path: string) => void,
): { browse: Browse; open: (path: string | null) => void } {
  const api = useApi();
  const [target, setTarget] = useState<Target>({ path: initialPath });
  const [browse, setBrowse] = useState<Browse>(LOADING);

  useEffect(() => {
    const controller = new AbortController();
    api.listDirectory(target.path, controller.signal).then(
      (listing) => {
        if (!controller.signal.aborted) {
          setBrowse({ status: "loaded", listing });
          onLoaded(listing.path);
        }
      },
      (cause: unknown) => {
        if (!controller.signal.aborted) {
          setBrowse({ status: "failed", message: errorMessage(cause) });
        }
      },
    );
    return () => controller.abort();
  }, [api, target, onLoaded]);

  const open = useCallback((path: string | null) => {
    setTarget({ path });
    setBrowse(LOADING);
  }, []);

  return { browse, open };
}
