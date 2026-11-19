<script lang="ts">
  export let name = '';
  export let size = 20;
  export let stroke = 1.65;
  const paths: Record<string, string[]> = {
    plus: ['M12 5v14M5 12h14'],
    arrow: ['M12 19V5m-5 5 5-5 5 5'],
    chevron: ['m9 5 7 7-7 7'],
    down: ['m6 9 6 6 6-6'],
    search: [
      'm21 21-4.4-4.4',
      'M19 10.5a8.5 8.5 0 1 1-17 0 8.5 8.5 0 0 1 17 0',
    ],
    panel: [
      'M9 3v18',
      'M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2',
    ],
    folder: [
      'M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z',
    ],
    chat: [
      'M21 11.5a8.4 8.4 0 0 1-9 8.5 9 9 0 0 1-4-.9L3 21l1.5-5A9 9 0 1 1 21 11.5Z',
    ],
    code: ['m8 7-5 5 5 5m8-10 5 5-5 5m-3-13-2 16'],
    spark: ['m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4L12 3Z'],
    sun: [
      'M12 3v2m0 14v2M3 12h2m14 0h2M5.6 5.6 7 7m10 10 1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4',
      'M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0',
    ],
    moon: ['M20.9 13A9 9 0 0 1 11 3.1 9 9 0 1 0 20.9 13Z'],
    brain: [
      'M12 18V5a3 3 0 0 0-5.8-1A4 4 0 0 0 4 11a4 4 0 0 0 1 7.5A3.5 3.5 0 0 0 12 18Zm0 0V5a3 3 0 0 1 5.8-1A4 4 0 0 1 20 11a4 4 0 0 1-1 7.5A3.5 3.5 0 0 1 12 18Z',
      'm8 8 4 2 4-2M8 15l4-2 4 2',
    ],
    paperclip: [
      'm8 12 6-6a3 3 0 0 1 4 4l-8 8a5 5 0 0 1-7-7l9-9a2 2 0 0 1 7 7l-9 9a1 1 0 0 1-3-3l8-8',
    ],
    close: ['m6 6 12 12M6 18 18 6'],
    check: ['m5 12 4 4L19 6'],
    copy: ['M9 9h11v12H9V9Z', 'M15 9V3H3v12h6'],
    refresh: [
      'M20 7v5h-5M4 17v-5h5',
      'M6 7a7 7 0 0 1 12-2l2 3M4 16l2 3a7 7 0 0 0 12-2',
    ],
    thumbs: [
      'M7 10v11H3V10h4Zm0 0 5-7a2 2 0 0 1 2 2v4h5a2 2 0 0 1 2 2l-2 8a2 2 0 0 1-2 2H7',
    ],
    external: [
      'M14 3h7v7m-10 3L21 3',
      'M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5',
    ],
    file: ['M14 2H5v20h14V7l-5-5Zm0 0v6h5M8 13h8m-8 4h5'],
    grid: ['M3 3h7v7H3V3Zm11 0h7v7h-7V3ZM3 14h7v7H3v-7Zm11 0h7v7h-7v-7Z'],
    clock: ['M12 7v5l3 2', 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0'],
    user: [
      'M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Zm4 14H4v-1a5 5 0 0 1 5-5h6a5 5 0 0 1 5 5v1Z',
    ],
    settings: [
      'm10 3-.7 2.3-2 .9L5 5.5 3 9l1.6 1.7v2.6L3 15l2 3.5 2.3-.7 2 .9L10 21h4l.7-2.3 2-.9 2.3.7 2-3.5-1.6-1.7v-2.6L21 9l-2-3.5-2.3.7-2-.9L14 3h-4Z',
      'M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
    ],
    trash: ['M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7'],
    leaf: ['M20 3C5 2 1 10 6 16s16 2 14-13Z', 'M5 21 16 8'],
    book: [
      'M12 5v16M3 3c4-1 7 0 9 2 2-2 5-3 9-2v16c-4-1-7 0-9 2-2-2-5-3-9-2V3Z',
    ],
    download: ['M12 3v12m-5-5 5 5 5-5M3 15v6h18v-6'],
    more: ['M5 12h.01M12 12h.01M19 12h.01'],
  };
</script>

<svg
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width={stroke}
  stroke-linecap="round"
  stroke-linejoin="round"
  aria-hidden="true"
>
  {#each paths[name] ?? paths.spark as d}<path {d} />{/each}
</svg>
