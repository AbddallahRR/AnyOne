# Plan Detallado: Migración Frontend a React Native (Expo + RN Web)

## Arquitectura General

```
anyone-mobile/                       # Nuevo proyecto Expo
├── app/                             # Expo Router (file-based routing)
│   ├── _layout.tsx                  # Root layout (tabs + providers)
│   ├── (tabs)/
│   │   ├── _layout.tsx              # Tab layout (anime/manga/library)
│   │   ├── index.tsx                # Tab Anime search
│   │   ├── manga.tsx                # Tab Manga search
│   │   └── library.tsx              # Tab Library
│   ├── serie/[type]/[source]/[id].tsx      # Serie detail
│   ├── reader/[type]/[source]/[contentId]/[chapter].tsx  # Reader
│   └── settings/
│       └── index.tsx                # Settings (tabs internas)
├── src/
│   ├── api/
│   │   ├── client.ts                # API base (fetch wrapper)
│   │   ├── search.ts                # /api/search, /api/search-all-stream
│   │   ├── content.ts               # /api/content, /api/chapters
│   │   ├── library.ts               # /api/library, /api/library/status
│   │   ├── downloads.ts             # /api/download, /api/queue/status
│   │   ├── progress.ts              # /api/progress
│   │   ├── watched.ts               # /api/watched
│   │   ├── settings.ts              # /api/settings/sources
│   │   └── scraper-configs.ts       # /api/scraper-configs/*
│   ├── components/
│   │   ├── MediaCard.tsx            # Card with cover, title, chips
│   │   ├── ChapterPill.tsx          # Chapter list item
│   │   ├── ProgressBar.tsx          # Reusable progress bar
│   │   ├── LoadingSpinner.tsx       # Spinner component
│   │   ├── EmptyState.tsx           # Empty state placeholder
│   │   ├── Toast.tsx                # Toast notification
│   │   ├── ConfirmDialog.tsx        # Confirmation dialog
│   │   ├── SearchBar.tsx            # Source select + query input + button
│   │   ├── StatusFilterBar.tsx      # Library status filters (chips)
│   │   ├── DownloadIndicator.tsx    # Floating download queue indicator
│   │   ├── ScraperHealthIndicator.tsx # Floating scraper health indicator
│   │   ├── SourceToggle.tsx         # Toggle switch component
│   │   ├── StatusPopup.tsx          # Library status change popup
│   │   ├── HeroCard.tsx             # Serie detail hero section
│   │   └── Wizard/
│   │       ├── StepProgress.tsx     # Step indicator (1-6)
│   │       ├── StepBasicInfo.tsx    # Step 1
│   │       ├── StepSearch.tsx       # Step 2 (search URL + selectors)
│   │       ├── StepDetails.tsx      # Step 3
│   │       ├── StepChapters.tsx     # Step 4
│   │       ├── StepContent.tsx      # Step 5
│   │       ├── StepSummary.tsx      # Step 6
│   │       ├── TestPanel.tsx        # Test button + results preview
│   │       └── DetectSection.tsx    # Auto-detection UI
│   ├── hooks/
│   │   ├── useSearch.ts            # Search with SSE/polling
│   │   ├── useLibrary.ts           # Library data + filters
│   │   ├── useChapters.ts          # Chapter list with virtual scroll
│   │   ├── useProgress.ts          # Watch/read progress
│   │   ├── useQueueStatus.ts       # Download queue polling
│   │   ├── useScraperHealth.ts     # Scraper health polling
│   │   └── useDebounce.ts          # Debounce hook
│   ├── stores/
│   │   ├── libraryStore.ts         # Zustand store for library
│   │   ├── queueStore.ts           # Download queue state
│   │   └── settingsStore.ts        # App settings
│   ├── types/
│   │   ├── api.ts                  # API response types
│   │   └── scraper.ts              # Scraper config types
│   └── utils/
│       ├── constants.ts            # Colors, sizes, etc.
│       └── formatters.ts           # Text formatting helpers
├── assets/                         # Icons, splash, etc.
├── app.json                        # Expo config
├── package.json
└── tsconfig.json
```

Backend (Python) — **sin cambios**:
```
AnyOne/                             # Intacto
├── app.py, core/, routers/, sources/, tests/ ...
```

---

## Fase 1: Setup del proyecto Expo (1-2 días)

### 1.1 Crear proyecto
```bash
npx create-expo-app@latest anyone-mobile --template blank-typescript
cd anyone-mobile
npx expo install expo-router react-native-safe-area-context react-native-screens expo-linking expo-constants expo-status-bar
npx expo install react-native-web react-dom @expo/metro-runtime
```

### 1.2 Dependencias
```json
{
  "dependencies": {
    "expo": "~52.0.0",
    "expo-router": "~4.0.0",
    "expo-av": "~15.0.0",
    "expo-image": "~2.0.0",
    "expo-font": "~13.0.0",
    "expo-file-system": "~18.0.0",
    "expo-notifications": "~0.29.0",
    "expo-background-fetch": "~13.0.0",
    "expo-splash-screen": "~0.29.0",
    "react-native-web": "~0.19.0",
    "react-dom": "~18.3.0",
    "@tanstack/react-query": "^5.0.0",
    "zustand": "^5.0.0",
    "@expo/vector-icons": "^14.0.0",
    "react-native-reanimated": "~3.16.0",
    "react-native-gesture-handler": "~2.20.0",
    "react-native-safe-area-context": "~4.14.0",
    "react-native-screens": "~4.4.0"
  }
}
```

### 1.3 app.json key configs
```json
{
  "expo": {
    "name": "AnyOne",
    "slug": "anyone",
    "scheme": "anyone",
    "web": { "bundler": "metro", "output": "single" },
    "plugins": [
      "expo-router",
      "expo-av",
      "expo-background-fetch"
    ]
  }
}
```

### 1.4 Capa de API (src/api/client.ts)

```typescript
// Reemplaza api.js (34 lines) + añade tipado
const BASE_URL = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:5000';

class ApiClient {
  private baseUrl: string;
  constructor(baseUrl: string) { this.baseUrl = baseUrl; }

  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
    if (!res.ok) {
      let msg = `Error ${res.status}`;
      try { const body = await res.json(); msg = body.detail || body.error || msg; } catch {}
      throw new Error(msg);
    }
    return res.json();
  }

  get<T>(path: string) { return this.request<T>(path); }
  post<T>(path: string, body?: unknown) { return this.request<T>(path, { method: 'POST', body: JSON.stringify(body) }); }
  put<T>(path: string, body?: unknown) { return this.request<T>(path, { method: 'PUT', body: JSON.stringify(body) }); }
  del<T>(path: string) { return this.request<T>(path, { method: 'DELETE' }); }
}

export const api = new ApiClient(BASE_URL);
```

### 1.5 Navigation structure (app/_layout.tsx)

```typescript
// Root layout: wraps everything in QueryClientProvider + SafeAreaProvider
export default function RootLayout() {
  return (
    <QueryClientProvider client={queryClient}>
      <SafeAreaProvider>
        <Stack screenOptions={{ headerShown: false }} />
        <Toast />
      </SafeAreaProvider>
    </QueryClientProvider>
  );
}
```

---

## Fase 2: Screens core (1 semana)

### 2.1 Tab Layout (app/(tabs)/_layout.tsx)

**Actual:** `templates/index.html` (3 tabs: Anime, Manga, Library)
**RN:** Bottom tab navigator con 3 tabs

```typescript
export default function TabLayout() {
  return (
    <Tabs screenOptions={{
      tabBarStyle: { backgroundColor: '#13131e', borderTopColor: 'rgba(255,255,255,0.06)' },
      tabBarActiveTintColor: '#7c5cfc',
    }}>
      <Tabs.Screen name="index" options={{ title: 'Anime', tabBarIcon: ({color}) => <FilmIcon color={color} /> }} />
      <Tabs.Screen name="manga" options={{ title: 'Manga', tabBarIcon: ({color}) => <BookIcon color={color} /> }} />
      <Tabs.Screen name="library" options={{ title: 'Biblioteca', tabBarIcon: ({color}) => <LayersIcon color={color} /> }} />
    </Tabs>
  );
}
```

### 2.2 Anime/Manga Search Tabs (app/(tabs)/index.tsx + manga.tsx)

**Actual:** `app.js` lines 151-351 (search + search-all-stream + render)
**Estado global:** `currentType, _libraryItems` (6 vars globales)
**RN Component tree:**
```
SearchTab
├── SearchBar
│   ├── Picker (source selector)
│   ├── TextInput (query)
│   ├── Button "Buscar"
│   └── Button "Refresh"
├── FlatList (results)
│   └── MediaCard (with onPress → navigate to serie)
│       ├── Image (cover-lazy)
│       ├── Chip (type/source)
│       ├── Title
│       └── Button "Descargar todo"
```

**Data flow:**
```typescript
function useSearch(type: 'anime' | 'manga') {
  return useQuery({
    queryKey: ['search', type, source, query],
    queryFn: () => api.get<SearchResult[]>(`/api/search?...`),
    enabled: !!query,
  });
}
```

**SSE streaming** (`searchAllStream` lines 189-297):
```typescript
// Web: EventSource nativo
// iOS/Android: react-native-sse o polling
function useSearchAllStream(type: string, query: string) {
  const [results, setResults] = useState<SearchResult[]>([]);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (Platform.OS === 'web') {
      const es = new EventSource(`/api/search-all-stream?...`);
      es.addEventListener('results', (e) => { ... });
      es.addEventListener('done', () => { setDone(true); es.close(); });
      return () => es.close();
    } else {
      // Polling fallback
      const interval = setInterval(async () => { ... }, 2000);
      return () => clearInterval(interval);
    }
  }, [type, query]);

  return { results, done };
}
```

### 2.3 Library Tab (app/(tabs)/library.tsx)

**Actual:** `app.js` lines 364-766 (library load, filter, search, status popup)
**RN Component tree:**
```
LibraryTab
├── Header (title + count)
├── TextInput (local search with debounce)
├── StatusFilterBar (horizontal scrollable chips)
├── FlatList (differential render)
│   └── MediaCard (with resume + status tag button)
│       ├── Image (cover)
│       ├── StatusChip (overlay)
│       ├── Chapter resume button
│       └── Status tag button → opens StatusPopup
└── StatusPopup (modal on mobile)
```

**State management (Zustand):**
```typescript
interface LibraryState {
  items: LibraryItem[];
  statuses: Record<string, string>;
  filter: 'all' | 'watching' | 'completed' | 'pending' | 'none';
  searchQuery: string;
  loadLibrary: () => Promise<void>;
  setStatus: (ref: string, status: string) => Promise<void>;
  applyFilter: (filter: string) => void;
}
```

**Differential render:** Actual `app.js` lines 471-563 compara `_renderedCards` Map con `nextIds`. En RN se hace con `FlatList` + `keyExtractor` + `extraData` — el renderizado diferencial lo maneja React Native automáticamente.

### 2.4 Serie Detail Screen (app/serie/[type]/[source]/[id].tsx)

**Actual:** `templates/serie.html` + `serie.js` (649 lines)
**RN Component tree:**
```
SerieScreen
├── ScrollView
│   ├── HeroCard
│   │   ├── Image (cover with parallax)
│   │   ├── Badge (anime/manga)
│   │   ├── Title
│   │   ├── Synopsis (expandable, lineClamp)
│   │   ├── ProgressSection
│   │   │   ├── ProgressBar
│   │   │   └── Chapter label
│   │   ├── DownloadProgress (conditional)
│   │   └── ActionButtons
│   │       ├── "Descargar serie"
│   │       ├── "Continuar"
│   │       ├── "Borrar vistos" (local only)
│   │       └── "Actualizar" (local with source)
│   └── ChaptersSection
│       ├── Header (count + sort toggle)
│       └── FlatList (virtualized chapters)
│           └── ChapterPill
│               ├── Number + watched dot
│               ├── Play/Stream button
│               ├── Download button
│               ├── Watched toggle (local)
│               └── Delete button (local)
```

**API calls in parallel** (serie.js lines 544-549):
```typescript
async function init() {
  const [details, chapters] = await Promise.all([
    api.get(`/api/content/${type}/${source}/${id}`),
    loadChapters(),  // includes watched in parallel internally
  ]);
  const progress = await loadProgress();
}
```

**Virtualized chapters** (serie.js lines 122-166: batch render + IntersectionObserver):
En RN se usa `FlatList` con `windowSize` y `onEndReached` — no necesita implementación manual.

### 2.5 Reader Screen (app/reader/[type]/[source]/[contentId]/[chapter].tsx)

**Actual:** `templates/reader.html` + `reader.js` (496 lines) + reader.css (190 lines)

#### Video Player (loadAnimeChapter lines 113-195)
```typescript
// RN: expo-av Video
import { Video, ResizeMode, AVPlaybackStatus } from 'expo-av';

function AnimeReader() {
  const videoRef = useRef<Video>(null);
  const [status, setStatus] = useState<AVPlaybackStatus>();

  // Auto-save progress every 15s (matching original)
  useEffect(() => {
    const interval = setInterval(async () => {
      if (status?.isLoaded && status.isPlaying) {
        const t = Math.floor(status.positionMillis / 1000);
        api.post(`/api/progress/anime/${source}/${contentId}`, { chapter, progress: t });
      }
    }, 15000);
    return () => clearInterval(interval);
  }, [status]);

  // Mark watched at 99%
  useEffect(() => {
    if (status?.isLoaded && status.durationMillis) {
      const pct = (status.positionMillis / status.durationMillis);
      if (pct >= 0.99) markCurrentAsWatched();
    }
  }, [status]);

  return (
    <Video
      ref={videoRef}
      source={{ uri: videoUrl }}
      resizeMode={ResizeMode.CONTAIN}
      useNativeControls
      onPlaybackStatusUpdate={setStatus}
      style={StyleSheet.absoluteFill}
    />
  );
}
```

#### Manga Reader (loadMangaChapter lines 214-473)
**Actual:** Sistema complejo con virtual windowing manual (WINDOW=2), prefix sums, binary search, image decode timeouts, prefetch.

**RN:** Se simplifica enormemente usando:
- `FlatList` con imágenes (ya tiene virtualización)
- `expo-image` para carga eficiente con caché
- `onViewableItemsChanged` para saber qué página es visible
- Prefetch con `Image.prefetch()`

```typescript
function MangaReader({ imageUrls }: { imageUrls: string[] }) {
  const flatRef = useRef<FlatList>(null);
  const [visibleIndex, setVisibleIndex] = useState(0);

  // Save progress on scroll
  const onViewableItemsChanged = useCallback(({ viewableItems }) => {
    if (viewableItems.length > 0) {
      const idx = viewableItems[0].index ?? 0;
      setVisibleIndex(idx);
      debouncedSave(idx);
    }
  }, []);

  // Mark watched at 90%
  const onScroll = useCallback((e: NativeSyntheticEvent<NativeScrollEvent>) => {
    const { contentOffset, contentSize, layoutMeasurement } = e.nativeEvent;
    const pct = (contentOffset.y + layoutMeasurement.height) / contentSize.height;
    if (pct >= 0.9) markCurrentAsWatched();
  }, []);

  return (
    <FlatList
      ref={flatRef}
      data={imageUrls}
      renderItem={({ item }) => (
        <Image source={{ uri: item }} style={{ width: '100%', height: undefined, aspectRatio: 2/3 }} />
      )}
      onViewableItemsChanged={onViewableItemsChanged}
      onScroll={onScroll}
      viewabilityConfig={{ itemVisiblePercentThreshold: 50 }}
      windowSize={3}
      initialScrollIndex={savedIndex}
      getItemLayout={(_, index) => ({ length: IMG_HEIGHT, offset: IMG_HEIGHT * index, index })}
    />
  );
}
```

**Navigation (prev/next chapter):** Same as `reader.js` lines 47-110.

**Full-screen:** Web: `Fullscreen API`. Mobile: `expo-screen-orientation` + status bar hidden.

---

## Fase 3: Download Queue + Indicators (2-3 días)

### 3.1 Download Queue Indicator (replaces queue-indicator.js 433 lines)

**Actual:** Floating indicator + popup con polling every 2s
**RN:** `React Query` polling + `expo-notifications` + badge en tab

```typescript
function useQueueStatus() {
  return useQuery({
    queryKey: ['queue-status'],
    queryFn: () => api.get<QueueStatus>('/api/queue/status'),
    refetchInterval: 2000, // poll every 2s
  });
}
```

**Componentes:**
```
DownloadIndicator (floating badge)
├── Active downloads count badge
├── onPress → expand modal
└── Modal
    ├── Section "Descargando ahora"
    ├── Section "En cola"
    └── Section "Errores"
```

### 3.2 Scraper Health Indicator (replaces scraper-health.js 421 lines)

**Actual:** Floating error indicator + popup con polling
**RN:** Same pattern as queue indicator

```
ScraperHealthIndicator
├── Red dot with count (left side)
└── Modal
    ├── List of failed/disabled sources
    └── "Reactivar" button per source
```

---

## Fase 4: Settings Screen (3-4 días)

### 4.1 Settings Layout (replaces settings.html + settings.js 1122 lines)

**Actual:** Sidebar tabs (Sources, Generator) + wizard
**RN:** Stack navigator con tabs horizontales

```
SettingsScreen
├── Tabs: "Fuentes" | "Generador"
├── SourcesTab
│   ├── List of source cards
│   │   ├── Icon (anime/manga)
│   │   ├── Label + URL + health dot
│   │   ├── Edit button → opens wizard
│   │   ├── Delete button
│   │   └── Toggle switch
│   └── "Nueva fuente" button
└── GeneratorTab
    └── Wizard
        ├── StepProgress (1-6 progress indicator)
        ├── StepBasicInfo (name, label, type, base URL)
        ├── StepSearch/Catalog (URL + selectors + Auto-detect)
        ├── StepDetails (URL + selectors)
        ├── StepChapters (URL + selectors + pagination)
        ├── StepContent (URL + selectors + content type)
        └── StepSummary (review + save)
```

### 4.2 Wizard Form Steps

**Actual:** Cada paso collectStepData() + validateStep() + showStep()
**RN:** Multi-step form con `react-hook-form` o state manual

Each step:
```
WizardStep
├── Fields (TextInput, Picker, Switch)
├── Auto-detect section (text-based selector detection)
├── TestPanel
│   ├── Input (content ID / query)
│   ├── "Test" button → calls /api/scraper-configs/test
│   └── Results preview (cards, images, chapters table)
└── Navigation (Prev / Next / Save)
```

### 4.3 Auto-detect Selectors (settings.js lines 718-906)

**API:** `POST /api/scraper-configs/detect-selectors`
**RN:** Same flow — fill URL template, send sample text, receive selectors, auto-fill fields.

### 4.4 Test Panels (settings.js lines 569-706)

**API:** `POST /api/scraper-configs/test`
Results render in RN:
- Search: ScrollView with MediaCard previews
- Details: Cover image + title + synopsis
- Chapters: Table with chapter numbers
- Content: Image grid or video URL

---

## Fase 5: Background Tasks + Notifications (1-2 días)

### 5.1 Background Updates Check (replaces serie.js checkForUpdates)

```typescript
// expo-background-fetch
export async function registerBackgroundFetchAsync() {
  return BackgroundFetch.registerTaskAsync('CHECK_UPDATES', {
    minimumInterval: 60 * 60, // 1 hour
    stopOnTerminate: false,
    startOnBoot: true,
  });
}

// When new chapters found → local push notification
async function checkAllUpdates() {
  const data = await api.get('/api/library/check-all-updates');
  if (data.total > 0) {
    await Notifications.scheduleNotificationAsync({
      content: {
        title: 'Nuevos capítulos disponibles',
        body: `${data.total} series tienen capítulos nuevos`,
      },
      trigger: null,
    });
  }
}
```

### 5.2 Push Notifications

**Actual:** Badge en tab (app.js lines 403-438)
**RN:** `expo-notifications` badge + notification when download completes

---

## Fase 6: Shared Utilities

### 6.1 Theme / Constants (replaces base.css design tokens)

```typescript
// src/utils/constants.ts
export const colors = {
  ink: '#0d0d14',
  surface: '#13131e',
  raised: '#1a1a28',
  text: '#f0f0f8',
  muted: '#6e6e88',
  accent: '#7c5cfc',
  accent2: '#fc5c8a',
  success: '#34d399',
  warn: '#fbbf24',
  danger: '#f87171',
};

export const spacing = { xs: 4, sm: 8, md: 12, lg: 16, xl: 24 };
export const radii = { card: 18, pill: 100, sm: 12, xs: 8 };
```

### 6.2 CSS → StyleSheet Mapping

| CSS Class | StyleSheet |
|---|---|
| `.chip` | `chip: { flexDirection: 'row', alignItems: 'center', height: 26, borderRadius: 100, paddingHorizontal: 10 }` |
| `.chip-anime` | `{ backgroundColor: 'rgba(124,92,252,0.50)', borderColor: 'rgba(124,92,252,0.3)' }` |
| `.media-card` | `mediaCard: { borderRadius: 18, overflow: 'hidden', backgroundColor: '#1a1a28' }` |
| `.card-image` | `{ aspectRatio: 2/3, overflow: 'hidden' }` |
| `.chapter-pill` | `chapterPill: { borderRadius: 12, padding: 10, flexDirection: 'row', justifyContent: 'space-between' }` |
| `.tab-nav` | `tabNav: { flexDirection: 'row', borderRadius: 100, backgroundColor: '#13131e', padding: 4 }` |
| `.progress-bar` | `progressBar: { height: 3, borderRadius: 2, backgroundColor: 'rgba(255,255,255,0.06)' }` |
| `.loading-spinner` | ActivityIndicator from RN |

### 6.3 Icon Mapping

| Actual (FontAwesome) | RN (@expo/vector-icons) |
|---|---|
| `fa-film` | `FontAwesome5 name="film"` |
| `fa-book` | `FontAwesome5 name="book"` |
| `fa-layer-group` | `FontAwesome5 name="layer-group"` |
| `fa-search` | `FontAwesome5 name="search"` |
| `fa-download` | `FontAwesome5 name="download"` |
| `fa-play` | `FontAwesome5 name="play"` |
| `fa-trash-alt` | `FontAwesome5 name="trash-alt"` |
| `fa-check` | `FontAwesome5 name="check"` |
| `fa-eye` | `FontAwesome5 name="eye"` |
| `fa-sync-alt` | `FontAwesome5 name="sync"` |
| `fa-arrow-left` | `FontAwesome5 name="arrow-left"` |
| `fa-expand` | `FontAwesome5 name="expand"` |
| `fa-chevron-left` | `FontAwesome5 name="chevron-left"` |
| `fa-chevron-right` | `FontAwesome5 name="chevron-right"` |
| `fa-pen` | `FontAwesome5 name="pen"` |
| `fa-copy` | `FontAwesome5 name="copy"` |
| `fa-tag` | `FontAwesome5 name="tag"` |
| `fa-clock` | `FontAwesome5 name="clock"` |
| `fa-check-circle` | `FontAwesome5 name="check-circle"` |
| `fa-exclamation-triangle` | `FontAwesome5 name="exclamation-triangle"` |
| `fa-exclamation-circle` | `FontAwesome5 name="exclamation-circle"` |
| `fa-folder-open` | `FontAwesome5 name="folder-open"` |
| `fa-filter` | `FontAwesome5 name="filter"` |
| `fa-rotate-right` | `FontAwesome5 name="redo"` |
| `fa-sort` | `FontAwesome5 name="sort"` |
| `fa-inbox` | `FontAwesome5 name="inbox"` |
| `fa-spinner` | `ActivityIndicator` |
| `fa-compress` | `FontAwesome5 name="compress"` |

---

## Fase 7: Responsive / Cross-platform Strategy

| Device | Strategy |
|---|---|
| **Web** | React Native Web con `react-native-web`. Layout usa `useWindowDimensions` + breakpoints. Full-screen reader usa `Fullscreen API`. |
| **iOS** | Expo managed. Video con `expo-av` (native controls). Manga reader con `FlatList`. Background tasks con `expo-background-fetch`. |
| **Android** | Same as iOS. Back button handled by `expo-router`. |

**Responsive breakpoints** (from CSS `@media` queries):
```typescript
const { width } = useWindowDimensions();
const isMobile = width < 480;
const isTablet = width >= 768;
const isDesktop = width >= 1024;
// Use in StyleSheet.create() or inline
```

**Media grid columns:**
```typescript
const numColumns = isMobile ? 2 : isTablet ? 3 : isDesktop ? 4 : 3;
```

---

## Resumen de APIs que el frontend RN debe consumir

| API Endpoint | RN Module | Uso |
|---|---|---|
| `GET /api/search` | `src/api/search.ts` | Búsqueda por fuente |
| `GET /api/search-all-stream` | `src/api/search.ts` | Búsqueda streaming (SSE) |
| `GET /api/content/...` | `src/api/content.ts` | Detalles de serie |
| `GET /api/chapters/...` | `src/api/content.ts` | Lista de capítulos |
| `GET /api/play/...` | `src/api/content.ts` | URLs de video/imágenes |
| `GET /api/manga/images/...` | `src/api/content.ts` | Imagen individual manga |
| `GET /api/video-duration/...` | `src/api/content.ts` | Duración video |
| `GET /api/library` | `src/api/library.ts` | Biblioteca local |
| `GET /api/library/status` | `src/api/library.ts` | Estados de biblioteca |
| `POST /api/library/status` | `src/api/library.ts` | Cambiar estado |
| `GET /api/library/updates` | `src/api/library.ts` | Actualizaciones |
| `POST /api/library/check-updates/...` | `src/api/library.ts` | Check individual |
| `GET /api/library/check-all-updates` | `src/api/library.ts` | Check global |
| `POST /api/download` | `src/api/downloads.ts` | Encolar serie |
| `POST /api/download/chapter` | `src/api/downloads.ts` | Encolar capítulo |
| `POST /api/download/chapters` | `src/api/downloads.ts` | Encolar múltiples |
| `GET /api/queue/status` | `src/api/downloads.ts` | Estado cola |
| `GET /api/progress/...` | `src/api/progress.ts` | Obtener progreso |
| `POST /api/progress/...` | `src/api/progress.ts` | Guardar progreso |
| `GET /api/watched/...` | `src/api/watched.ts` | Capítulos vistos |
| `POST /api/watched` | `src/api/watched.ts` | Marcar visto |
| `POST /api/watched/toggle` | `src/api/watched.ts` | Toggle visto |
| `POST /api/delete-watched` | `src/api/watched.ts` | Borrar vistos |
| `POST /api/delete-chapter` | `src/api/watched.ts` | Borrar capítulo |
| `GET /api/settings/sources` | `src/api/settings.ts` | Fuentes activas |
| `PUT /api/settings/sources/{name}` | `src/api/settings.ts` | Toggle fuente |
| `GET /api/scraper-configs` | `src/api/scraper-configs.ts` | Listar configs |
| `GET /api/scraper-configs/{name}` | `src/api/scraper-configs.ts` | Obtener config |
| `POST /api/scraper-configs` | `src/api/scraper-configs.ts` | Crear |
| `PUT /api/scraper-configs/{name}` | `src/api/scraper-configs.ts` | Actualizar |
| `DEL /api/scraper-configs/{name}` | `src/api/scraper-configs.ts` | Eliminar |
| `POST /api/scraper-configs/test` | `src/api/scraper-configs.ts` | Probar scraper |
| `POST /api/scraper-configs/check-url` | `src/api/scraper-configs.ts` | Verificar URL |
| `POST /api/scraper-configs/detect-selectors` | `src/api/scraper-configs.ts` | Auto-detectar |
| `GET /api/scraper-health` | `src/api/scraper-configs.ts` | Health |
| `POST /api/scraper-health/re-enable` | `src/api/scraper-configs.ts` | Re-activar |

---

## Lo que NO cambia del backend

| Componente | Estado |
|---|---|
| `app.py` (FastAPI app) | ✅ Sin cambios |
| `routers/pages.py` (SSR) | ✅ Se mantiene (sirve web actual) |
| `routers/api/*` (REST) | ✅ Sin cambios |
| `core/*` (lógica) | ✅ Sin cambios |
| `sources/*` (scrapers) | ✅ Sin cambios |
| `templates/*` | ✅ Se mantienen (backward compat) |
| `static/css/*` | ✅ Se mantienen (backward compat) |
| `static/js/*` | ✅ Se mantienen (backward compat) |
| SQLite DB | ✅ Sin cambios |
| Dockerfile | ✅ Sin cambios |

---

## Estimación de esfuerzo

| Fase | Días | Archivos | Líneas estimadas |
|---|---|---|---|
| F1: Setup + API client + Providers | 1-2 | ~10 | ~300 |
| F2: Screens core (search + library + serie) | 5-7 | ~20 | ~2000 |
| F3: Reader (video + manga) | 3-4 | ~5 | ~800 |
| F4: Download + Health indicators | 2-3 | ~6 | ~600 |
| F5: Settings + Wizard | 4-5 | ~25 | ~2500 |
| F6: Background tasks + Notifications | 1-2 | ~4 | ~300 |
| F7: Polishing (animations, responsive, testing) | 2-3 | ~10 | ~500 |

**Total: ~18-26 días hábiles (~3-5 semanas)**

---

## Conclusión

**Sí, es totalmente factible.** El backend no requiere cambios. La migración a Expo + React Native Web permite compartir ~90% del código entre iOS, Android y Web. Los mayores desafíos son:

1. **SSE streaming** en móvil — resuelto con polling o `react-native-sse`
2. **Wizard de 6 pasos** — resuelto con multi-step form component
3. **Manga reader virtualizado** — RN FlatList lo maneja mejor que la implementación manual actual
4. **Descargas en segundo plano** — limitado en iOS, pero funcional con `expo-background-fetch`

El resultado será una app nativa con la misma funcionalidad y una experiencia mobile-first superior.
