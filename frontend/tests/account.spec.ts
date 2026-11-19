import { test, expect, type Page } from '@playwright/test';

async function openSettings(page: Page) {
  await page.getByRole('button', { name: 'Open workspace settings' }).click();
  const settings = page.getByRole('dialog', { name: 'Workspace settings' });
  await expect(settings).toBeVisible();
  return settings;
}

test('demo sign-in and sign-out survive a reload without Google requests', async ({
  page,
}) => {
  const googleRequests: string[] = [];
  await page.route('https://accounts.google.com/**', (route) => {
    googleRequests.push(route.request().url());
    return route.abort();
  });
  const apiRequests: string[] = [];
  await page.route('**/api/auth/**', (route) => {
    apiRequests.push(route.request().url());
    return route.fulfill({ status: 401 });
  });
  await page.goto('/');
  const settings = await openSettings(page);
  test.skip(
    !(await settings.getByText('Google sign-in demo').isVisible()),
    'Requires running without VITE_GOOGLE_CLIENT_ID',
  );
  await expect(settings.getByText('Guest', { exact: true })).toBeVisible();
  await settings.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(settings.getByText('Demo User')).toBeVisible();

  await page.reload();
  await openSettings(page);
  await expect(settings.getByText('Demo User')).toBeVisible();
  await settings.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(settings.getByText('Guest', { exact: true })).toBeVisible();

  await page.reload();
  await openSettings(page);
  await expect(settings.getByText('Guest', { exact: true })).toBeVisible();
  expect(googleRequests).toEqual([]);
  expect(apiRequests).toEqual([]);
});

test('configured Google sign-in trusts the API and restores its session after reload', async ({
  page,
}) => {
  await page.addInitScript(() => {
    sessionStorage.setItem('kett-google-profile-v1', 'Untrusted Old Profile');
  });
  await page.route('https://accounts.google.com/gsi/client', (route) =>
    route.fulfill({
      contentType: 'application/javascript',
      body: `
        let attempts = 0;
        let config;
        window.google = { accounts: { id: {
          initialize(options) {
            if (!options.client_id || options.nonce !== 'test-nonce') throw new Error();
            config = options;
          },
          renderButton(target) {
            const button = document.createElement('button');
            button.textContent = 'Sign in with Google';
            button.onclick = () => {
              if (++attempts !== 1) config.callback({ credential: 'test-id-token' });
            };
            target.append(button);
          }
        }}};
      `,
    }),
  );
  const user = { id: 1, name: 'Google Test User', email: null };
  const credentials: unknown[] = [];
  let signedIn = false;
  await page.route('**/api/auth/me', (route) =>
    signedIn
      ? route.fulfill({ json: user })
      : route.fulfill({ status: 401, json: { detail: 'Not signed in' } }),
  );
  await page.route('**/api/auth/google/challenge', (route) =>
    route.fulfill({ json: { nonce: 'test-nonce' } }),
  );
  await page.route('**/api/auth/google', (route) => {
    credentials.push(route.request().postDataJSON());
    signedIn = credentials.length > 1;
    return signedIn
      ? route.fulfill({ json: user })
      : route.fulfill({ status: 401, json: { detail: 'Invalid credential' } });
  });
  await page.route('**/api/auth/logout', (route) => {
    expect(route.request().method()).toBe('POST');
    signedIn = false;
    return route.fulfill({ status: 204 });
  });

  await page.goto('/');
  const settings = await openSettings(page);
  test.skip(
    await settings.getByText('Google sign-in demo').isVisible(),
    'Requires VITE_GOOGLE_CLIENT_ID; Google and API requests are mocked',
  );
  const signIn = settings.getByRole('button', { name: 'Sign in with Google' });
  await signIn.click(); // The mock simulates closing the Google popup.
  await expect(settings.getByText('Guest', { exact: true })).toBeVisible();
  expect(credentials).toHaveLength(0);

  await signIn.click();
  await expect(settings.getByRole('alert')).toHaveText(
    'Google sign-in failed. Please try again.',
  );
  await settings.getByRole('button', { name: 'Retry' }).click();
  await signIn.click();
  await expect(settings.getByText(user.name)).toBeVisible();
  expect(credentials).toEqual([
    { credential: 'test-id-token' },
    { credential: 'test-id-token' },
  ]);
  const storage = await page.evaluate(() =>
    JSON.stringify([sessionStorage, localStorage]),
  );
  expect(storage).not.toContain('test-id-token');
  expect(storage).not.toContain(user.name);

  await page.reload();
  await openSettings(page);
  await expect(settings.getByText(user.name)).toBeVisible();
  await settings.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(settings.getByText('Guest', { exact: true })).toBeVisible();
  expect(signedIn).toBe(false);

  await page.reload();
  await openSettings(page);
  await expect(signIn).toBeVisible();
  await expect(settings.getByText('Guest', { exact: true })).toBeVisible();
});
