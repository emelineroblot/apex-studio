// Polyfill IndexedDB pour `lib/upload/db.ts` (jsdom ne l'implémente pas) — nécessaire
// pour tester la file d'upload sans mocker `indexedDB` à la main.
import "fake-indexeddb/auto";
