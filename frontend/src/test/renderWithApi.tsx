import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { ApiProvider } from "../api/ApiContext";
import type { Api } from "../api/client";

/** 画面の部品を、偽物の API を渡して描く。 */
export function renderWithApi(ui: ReactElement, api: Api) {
  return render(<ApiProvider api={api}>{ui}</ApiProvider>);
}
