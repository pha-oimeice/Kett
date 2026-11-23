type GoogleIdentity = {
  initialize(config: {
    client_id: string;
    nonce: string;
    callback: (response: { credential: string }) => void;
  }): void;
  renderButton(
    target: HTMLElement,
    config: { theme: 'outline'; size: 'medium' },
  ): void;
};

export type UserProfile = { id: number; name: string; email: string | null };

function getGoogleIdentity() {
  return (
    window as Window & { google?: { accounts?: { id?: GoogleIdentity } } }
  ).google?.accounts?.id;
}

const AUTH_TIMEOUT = 15_000;
let sdk: Promise<GoogleIdentity> | undefined;
let pendingChallenge: Promise<string> | undefined;

function loadGoogleIdentity() {
  const existing = getGoogleIdentity();
  if (existing) return Promise.resolve(existing);
  sdk ??= new Promise<GoogleIdentity>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    const fail = () => {
      clearTimeout(deadline);
      script.onload = script.onerror = null;
      script.remove();
      sdk = undefined;
      reject(new Error('Google Identity Services could not be loaded'));
    };
    const deadline = window.setTimeout(fail, AUTH_TIMEOUT);
    script.onload = () => {
      clearTimeout(deadline);
      const identity = getGoogleIdentity();
      if (identity) resolve(identity);
      else fail();
    };
    script.onerror = fail;
    document.head.append(script);
  });
  return sdk;
}

function authRequest(endpoint: string, options?: RequestInit) {
  return fetch(`/api/auth/${endpoint}`, {
    ...options,
    credentials: 'same-origin',
    cache: 'no-store',
    redirect: 'error',
    signal: AbortSignal.timeout(AUTH_TIMEOUT),
  });
}

async function requestChallenge() {
  const response = await authRequest('google/challenge', { method: 'POST' });
  if (!response.ok) throw new Error('Could not start Google sign-in');
  const { nonce } = await response.json();
  if (typeof nonce !== 'string' || !nonce)
    throw new Error('No Google sign-in challenge');
  return nonce;
}

export async function renderGoogleSignIn(
  target: HTMLElement,
  clientId: string,
  onCredential: (credential: string) => void,
) {
  const identity = await loadGoogleIdentity();
  if (!target.isConnected) return;
  // A quick close/reopen can mount a new button while the old request is
  // pending. Share that request so its Set-Cookie cannot replace a newer nonce.
  pendingChallenge ??= requestChallenge().finally(() => {
    pendingChallenge = undefined;
  });
  const nonce = await pendingChallenge;
  if (!target.isConnected) return;
  identity.initialize({
    client_id: clientId,
    nonce,
    callback: ({ credential }) => {
      if (target.isConnected && credential) onCredential(credential);
    },
  });
  identity.renderButton(target, { theme: 'outline', size: 'medium' });
}

async function readProfile(response: Response): Promise<UserProfile> {
  const profile = await response.json();
  if (
    !profile ||
    !Number.isSafeInteger(profile.id) ||
    typeof profile.name !== 'string' ||
    !profile.name ||
    (profile.email !== null && typeof profile.email !== 'string')
  )
    throw new Error('Invalid account profile');
  return profile;
}

export class GoogleSignInUnavailable extends Error {}

export async function signInWithGoogle(
  credential: string,
): Promise<UserProfile> {
  const response = await authRequest('google', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential }),
  });
  if (response.status === 503) throw new GoogleSignInUnavailable();
  if (!response.ok) throw new Error('Google credential was not accepted');
  return readProfile(response);
}

export async function getCurrentUser(): Promise<UserProfile | null> {
  const response = await authRequest('me');
  if (response.status === 401) return null;
  if (!response.ok) throw new Error('Could not check the current session');
  return readProfile(response);
}

export async function signOut() {
  const response = await authRequest('logout', { method: 'POST' });
  if (!response.ok) throw new Error('Could not sign out');
}
