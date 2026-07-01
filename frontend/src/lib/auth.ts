import {
  startRegistration,
  startAuthentication,
} from "@simplewebauthn/browser";
import { api } from "./api";

// py_webauthn's options_to_json returns the JSON option objects SimpleWebAuthn
// expects. v11 takes { optionsJSON }.

export async function registerPasskey(displayName: string, inviteCode?: string) {
  const options = await api.post("/auth/register/begin", {
    display_name: displayName,
    invite_code: inviteCode,
  });
  const credential = await startRegistration({ optionsJSON: options });
  return api.post("/auth/register/complete", { credential });
}

export async function loginPasskey() {
  const options = await api.post("/auth/login/begin", {});
  const credential = await startAuthentication({ optionsJSON: options });
  return api.post("/auth/login/complete", { credential });
}

export async function addPasskey(name?: string) {
  const options = await api.post("/auth/passkey/add/begin", {});
  const credential = await startRegistration({ optionsJSON: options });
  return api.post("/auth/passkey/add/complete", { credential, name });
}

export async function recoverWithCode(code: string) {
  return api.post("/auth/recover", { code });
}

export type PasskeyInfo = {
  id: string;
  name: string;
  created_at: string;
  last_used_at: string | null;
};

export async function listPasskeys(): Promise<PasskeyInfo[]> {
  return api.get("/auth/passkeys");
}

export async function deletePasskey(id: string) {
  return api.del(`/auth/passkeys/${id}`);
}

export async function regenerateRecoveryCodes(): Promise<string[]> {
  const res = await api.post("/auth/recovery-codes/regenerate", {});
  return res.recovery_codes as string[];
}

export function passkeysSupported(): boolean {
  return typeof window !== "undefined" && !!window.PublicKeyCredential;
}
