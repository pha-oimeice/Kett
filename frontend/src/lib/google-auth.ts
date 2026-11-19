type GoogleOAuth = {
  initTokenClient(config: {
    client_id: string;
    scope: string;
    include_granted_scopes: boolean;
    callback: (response: { access_token?: string; error?: string }) => void;
    error_callback: (error: { type: string }) => void;
  }): { requestAccessToken(options: { prompt: string }): void };
};

function getGoogleOAuth() {
  return (
    window as Window & { google?: { accounts?: { oauth2?: GoogleOAuth } } }
  ).google?.accounts?.oauth2;
}

async function loadGoogleOAuth() {
  const existing = getGoogleOAuth();
  if (existing) return existing;

  const script = document.createElement('script');
  script.src = 'https://accounts.google.com/gsi/client';
  script.async = true;
  return new Promise<GoogleOAuth>((resolve, reject) => {
    const fail = () => {
      script.remove();
      reject(new Error('Google Identity Services could not be loaded'));
    };
    script.onload = () => {
      const oauth = getGoogleOAuth();
      if (oauth) resolve(oauth);
      else fail();
    };
    script.onerror = fail;
    document.head.append(script);
  });
}

export async function prepareGoogleSignIn(clientId: string) {
  const oauth = await loadGoogleOAuth();
  return async (): Promise<string | null> => {
    // Request the popup directly from the click, after the SDK is ready.
    const accessToken = await new Promise<string | null>((resolve, reject) => {
      oauth
        .initTokenClient({
          client_id: clientId,
          scope: 'openid profile',
          include_granted_scopes: false,
          callback: ({ access_token, error }) => {
            if (error === 'access_denied') resolve(null);
            else if (error || !access_token)
              reject(new Error('Google authorization failed'));
            else resolve(access_token);
          },
          error_callback: ({ type }) => {
            if (type === 'popup_closed') resolve(null);
            else reject(new Error('Google sign-in popup failed'));
          },
        })
        .requestAccessToken({ prompt: 'select_account' });
    });
    if (!accessToken) return null;

    const response = await fetch(
      'https://openidconnect.googleapis.com/v1/userinfo',
      {
        headers: { Authorization: `Bearer ${accessToken}` },
        credentials: 'omit',
        cache: 'no-store',
        redirect: 'error',
      },
    );
    if (!response.ok) throw new Error('Could not fetch the Google profile');
    const profile: { sub?: unknown; name?: unknown } = await response.json();
    if (typeof profile.sub !== 'string' || !profile.sub) {
      throw new Error('Invalid Google profile');
    }
    return (
      (typeof profile.name === 'string' && profile.name.trim()) ||
      'Google account'
    );
  };
}
