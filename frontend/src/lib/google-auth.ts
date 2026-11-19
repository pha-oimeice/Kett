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

type UserProfile = { id: number; name: string; email: string | null };

function getGoogleIdentity() {
  return (
    window as Window & { google?: { accounts?: { id?: GoogleIdentity } } }
  ).google?.accounts?.id;
}

let sdk: Promise<GoogleIdentity> | undefined;

function loadGoogleIdentity() {
  const existing = getGoogleIdentity();
  if (existing) return Promise.resolve(existing);
  sdk ??= new Promise<GoogleIdentity>((resolve, reject) => {
    const script = document.createElement('script');
    script.src = 'https://accounts.google.com/gsi/client';
    script.async = true;
    const fail = () => {
      script.remove();
      sdk = undefined;
      reject(new Error('Google Identity Services could not be loaded'));
    };
    script.onload = () => {
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
  });
}

export async function renderGoogleSignIn(
  target: HTMLElement,
  clientId: string,
  onCredential: (credential: string) => void,
) {
  const identity = await loadGoogleIdentity();
  if (!target.isConnected) return;
  const challenge = await authRequest('google/challenge', { method: 'POST' });
  if (!challenge.ok) throw new Error('Could not start Google sign-in');
  const { nonce }: { nonce: string } = await challenge.json();
  if (!nonce) throw new Error('No Google sign-in challenge');
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

export async function signInWithGoogle(
  credential: string,
): Promise<UserProfile> {
  const response = await authRequest('google', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ credential }),
  });
  if (!response.ok) throw new Error('Google credential was not accepted');
  return response.json();
}

export async function getCurrentUser(): Promise<UserProfile | null> {
  const response = await authRequest('me');
  if (response.status === 401) return null;
  if (!response.ok) throw new Error('Could not check the current session');
  return response.json();
}

export async function signOut() {
  const response = await authRequest('logout', { method: 'POST' });
  if (!response.ok) throw new Error('Could not sign out');
}
