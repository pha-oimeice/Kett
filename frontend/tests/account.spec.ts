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
});

test('configured Google sign-in handles cancellation and reads the profile without storing the token', async ({
  page,
}) => {
  await page.route('https://accounts.google.com/gsi/client', (route) =>
    route.fulfill({
      contentType: 'application/javascript',
      body: `
        let attempts = 0;
        window.google = { accounts: { oauth2: {
          initTokenClient(config) {
            if (!config.client_id || config.scope !== 'openid profile') throw new Error();
            return { requestAccessToken({ prompt }) {
              if (prompt !== 'select_account' || !navigator.userActivation.isActive) throw new Error();
              setTimeout(() => {
                if (++attempts === 1) config.error_callback({ type: 'popup_closed' });
                else config.callback({ access_token: 'test-access-token' });
              }, 20);
            }};
          }
        }}};
      `,
    }),
  );
  const profileRequests: (string | null)[] = [];
  await page.route(
    'https://openidconnect.googleapis.com/v1/userinfo',
    async (route) => {
      profileRequests.push(await route.request().headerValue('authorization'));
      return route.fulfill({
        status: profileRequests.length === 1 ? 503 : 200,
        headers: { 'Access-Control-Allow-Origin': '*' },
        json: { sub: 'google-test-user', name: 'Google Test User' },
      });
    },
  );

  await page.goto('/');
  const settings = await openSettings(page);
  test.skip(
    await settings.getByText('Google sign-in demo').isVisible(),
    'Requires VITE_GOOGLE_CLIENT_ID; Google requests are mocked',
  );
  const signIn = settings.getByRole('button', { name: 'Sign in', exact: true });
  await signIn.click();
  await expect(signIn).toBeEnabled();
  await expect(settings.getByText('Guest', { exact: true })).toBeVisible();
  expect(profileRequests).toHaveLength(0);

  await signIn.click();
  await expect(settings.getByRole('alert')).toHaveText(
    'Google sign-in failed. Please try again.',
  );
  await signIn.click();
  await expect(settings.getByText('Google Test User')).toBeVisible();
  expect(profileRequests).toEqual([
    'Bearer test-access-token',
    'Bearer test-access-token',
  ]);
  expect(
    await page.evaluate(() => JSON.stringify([sessionStorage, localStorage])),
  ).not.toContain('test-access-token');
  await settings.getByRole('button', { name: 'Sign out', exact: true }).click();
  await expect(settings.getByText('Guest', { exact: true })).toBeVisible();
});
