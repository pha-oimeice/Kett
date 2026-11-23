import { defineConfig, loadEnv } from 'vite';
import { svelte } from '@sveltejs/vite-plugin-svelte';

export default defineConfig(({ mode }) => {
  const googleClientId = loadEnv(
    mode,
    '.',
    'GOOGLE_CLIENT_ID',
  ).GOOGLE_CLIENT_ID?.trim();
  return {
    plugins: [svelte()],
    // Expose only the public OAuth client ID so the UI and API can share one setting.
    define: googleClientId
      ? {
          'import.meta.env.VITE_GOOGLE_CLIENT_ID':
            JSON.stringify(googleClientId),
        }
      : undefined,
    server: {
      proxy: { '/api': 'http://127.0.0.1:8000' },
    },
  };
});
