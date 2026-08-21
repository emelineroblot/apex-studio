/**
 * Base en mémoire du mode "fixtures" — conforme aux schémas de `services/api/openapi.json`.
 * Réinitialisée à chaque rechargement complet de page (pas de persistance au-delà de
 * `sessionStorage`/`localStorage` gérés ailleurs, ex. la file d'upload).
 *
 * `FixtureUser` rejoue localement `GET /users` (§ correction J1 — voir `implementation.md`) :
 * peuple le sélecteur d'affectation d'équipe (`PUT /shootings/{id}/staff`) sans appel réseau.
 */
import type {
  CameraOut,
  ClientOut,
  CircuitOut,
  CollectionOut,
  DemoAccount,
  DriverOut,
  EngagementOut,
  MediaOut,
  MediaSummary,
  OcrCandidateOut,
  OcrSettingsOut,
  ShootingOut,
  TeamOut,
  UserOut,
} from "@/lib/api/types";
import { placeholderImage } from "@/lib/api/fixtures/utils";

export type FixtureUser = UserOut;

/**
 * `uploaded_by` n'existe pas dans `MediaOut`/`MediaSummary` (hors contrat public) mais
 * conditionne la visibilité côté backend (`services/access.py::media_visibility_clause` :
 * un média `shooting_id IS NULL` reste visible par son déposant). Champ interne aux
 * fixtures uniquement, consommé par `fixtures/media.ts` pour rejouer cette règle — voir
 * `implementation.md`.
 */
export type MediaFixture = MediaOut & { uploaded_by: number };

export type FixtureBatch = {
  id: number;
  expected_count: number;
  received_count: number;
  status: "open" | "processing" | "closed";
  shooting_hint_id: number | null;
  started_at: string;
};

export const users: FixtureUser[] = [
  { id: 1, email: "camille.servan@apex-studio.demo", full_name: "Camille Servan", role: "owner" },
  {
    id: 2,
    email: "hugo.delacroix@apex-studio.demo",
    full_name: "Hugo Delacroix",
    role: "photographer",
  },
  { id: 3, email: "awa.ndiaye@apex-studio.demo", full_name: "Awa Ndiaye", role: "photographer" },
];

export const demoAccounts: DemoAccount[] = [
  {
    role: "owner",
    email: "camille.servan@apex-studio.demo",
    password: "demo-dirigeant",
    label: "Camille Servan — Dirigeante",
  },
  {
    role: "photographer",
    email: "hugo.delacroix@apex-studio.demo",
    password: "demo-photographe",
    label: "Hugo Delacroix — Photographe",
  },
];

/** Mots de passe acceptés en mode fixtures — miroir de `demoAccounts`. */
export const credentials = new Map(demoAccounts.map((a) => [a.email, a.password]));

export const clients: ClientOut[] = [
  {
    id: 1,
    name: "Écurie Vitesse Bleue",
    kind: "team",
    contact_name: "Nadia Lorrain",
    contact_email: "contact@vitessebleue.demo",
    phone: "+33 6 12 34 56 78",
    address: "12 rue du Paddock, 69000 Lyon",
    notes: "Client historique, 3 saisons.",
    created_at: "2025-02-10T09:00:00Z",
    updated_at: "2025-02-10T09:00:00Z",
  },
  {
    id: 2,
    name: "Team Chicane Racing",
    kind: "team",
    contact_name: "Marc Yildiz",
    contact_email: "marc@chicane-racing.demo",
    phone: "+33 6 98 76 54 32",
    address: null,
    notes: null,
    created_at: "2025-03-01T09:00:00Z",
    updated_at: "2025-03-01T09:00:00Z",
  },
  {
    id: 3,
    name: "Julien Farrow",
    kind: "driver",
    contact_name: null,
    contact_email: "julien.farrow@demo.fr",
    phone: "+33 6 11 22 33 44",
    address: null,
    notes: "Pilote indépendant, GT4.",
    created_at: "2025-03-15T09:00:00Z",
    updated_at: "2025-03-15T09:00:00Z",
  },
  {
    id: 4,
    name: "Nova Tires",
    kind: "sponsor",
    contact_name: "Service communication",
    contact_email: "presse@novatires.demo",
    phone: null,
    address: null,
    notes: "Demande systématiquement les plans serrés sur les pneus.",
    created_at: "2025-04-02T09:00:00Z",
    updated_at: "2025-04-02T09:00:00Z",
  },
];

export const circuits: CircuitOut[] = [
  { id: 1, name: "Circuit de Roquebrune", city: "Roquebrune", country: "France", timezone: "Europe/Paris" },
  { id: 2, name: "Anneau du Vercors", city: "Vif", country: "France", timezone: "Europe/Paris" },
  { id: 3, name: "Piste de Montclair", city: "Montclair", country: "France", timezone: "Europe/Paris" },
];

export const drivers: DriverOut[] = [
  { id: 1, full_name: "Julien Farrow", nationality: "FR" },
  { id: 2, full_name: "Léna Duchamp", nationality: "FR" },
  { id: 3, full_name: "Marco Vinci", nationality: "IT" },
  { id: 4, full_name: "Sacha Belmonte", nationality: "FR" },
  { id: 5, full_name: "Inès Cormier", nationality: "FR" },
];

export const teams: TeamOut[] = [
  { id: 1, name: "Écurie Vitesse Bleue", client_id: 1 },
  { id: 2, name: "Team Chicane Racing", client_id: 2 },
  { id: 3, name: "Nova Racing Sport", client_id: null },
];

export const cameras: CameraOut[] = [
  {
    id: 1,
    exif_serial: "CAN-8834211",
    make: "Canon",
    model: "EOS R6 Mark II",
    owner_user_id: 2,
    clock_offset_seconds: 0,
    timezone: "Europe/Paris",
  },
  {
    id: 2,
    exif_serial: "NIK-2210984",
    make: "Nikon",
    model: "Z9",
    owner_user_id: 3,
    clock_offset_seconds: -184,
    timezone: "Europe/Paris",
  },
];

export const shootings: ShootingOut[] = [
  {
    id: 1,
    client_id: 1,
    circuit_id: 1,
    title: "Course d'endurance — Roquebrune 6h",
    starts_at: "2026-06-13T07:00:00Z",
    ends_at: "2026-06-13T19:00:00Z",
    status: "done",
    quota_bytes: 2147483648,
    notes: "Accès paddock dès 6h. Prévoir batteries de secours.",
    staff: [
      { user_id: 2, role: "photographer" },
      { user_id: 3, role: "photographer" },
    ],
    engagement_count: 4,
  },
  {
    id: 2,
    client_id: 2,
    circuit_id: 2,
    title: "Manche championnat régional GT",
    starts_at: "2026-07-04T08:30:00Z",
    ends_at: "2026-07-04T17:00:00Z",
    status: "planned",
    quota_bytes: 2147483648,
    notes: null,
    staff: [{ user_id: 2, role: "photographer" }],
    engagement_count: 2,
  },
  {
    id: 3,
    client_id: null,
    circuit_id: 3,
    title: "Journée essais libres — clients privés",
    starts_at: "2026-05-02T09:00:00Z",
    ends_at: "2026-05-02T18:00:00Z",
    status: "done",
    quota_bytes: 1073741824,
    notes: "Shooting sans client attitré, engagements ajoutés à l'arrivée.",
    staff: [{ user_id: 3, role: "photographer" }],
    engagement_count: 1,
  },
];

export const engagements: EngagementOut[] = [
  { id: 1, shooting_id: 1, car_number: "12", driver_id: 1, team_id: 1, client_id: 1, car_model: "Porsche 911 GT3 Cup" },
  { id: 2, shooting_id: 1, car_number: "27", driver_id: 2, team_id: 1, client_id: 1, car_model: "Porsche 911 GT3 Cup" },
  { id: 3, shooting_id: 1, car_number: "5", driver_id: 3, team_id: 2, client_id: 2, car_model: "BMW M4 GT4" },
  { id: 4, shooting_id: 1, car_number: "44", driver_id: 4, team_id: 2, client_id: 2, car_model: "BMW M4 GT4" },
  { id: 5, shooting_id: 2, car_number: "5", driver_id: 3, team_id: 2, client_id: 2, car_model: "BMW M4 GT4" },
  { id: 6, shooting_id: 2, car_number: "9", driver_id: 5, team_id: 3, client_id: null, car_model: "Alpine A110 GT4" },
  { id: 7, shooting_id: 3, car_number: "3", driver_id: 1, team_id: null, client_id: 3, car_model: "Porsche Cayman GT4 CS" },
];

export const batches: FixtureBatch[] = [
  {
    id: 1,
    expected_count: 24,
    received_count: 24,
    status: "closed",
    shooting_hint_id: 1,
    started_at: "2026-06-13T19:05:00Z",
  },
];

function buildMedia(): MediaFixture[] {
  const list: MediaFixture[] = [];
  let id = 1;

  const push = (partial: Partial<MediaFixture> & Pick<MediaFixture, "id">) => {
    const base: MediaFixture = {
      id: partial.id,
      batch_id: 1,
      uploaded_by: 2,
      original_filename: `IMG_${1000 + partial.id}.jpg`,
      byte_size: 6_200_000,
      mime: "image/jpeg",
      width: 6000,
      height: 4000,
      shot_at_exif: "2026-06-13T09:12:00",
      shot_at: "2026-06-13T09:12:00Z",
      exif: {
        camera_id: 1,
        lens_model: "RF 70-200mm F2.8L",
        iso: 400,
        shutter_speed_sec: 0.001,
        shutter_speed_label: "1/1000",
        aperture: 2.8,
        focal_length: 135,
        gps_lat: null,
        gps_lon: null,
        exif_raw: null,
      },
      phash: null,
      sharpness: 210.4,
      series_id: null,
      is_series_representative: true,
      duplicate_of_media_id: null,
      ingest_status: "ingested",
      quarantine_reason: null,
      quarantine_detail: null,
      attachment_status: "shooting_attached",
      attachment_source: "pipeline_time",
      attachment_detail: null,
      shooting_id: 1,
      is_simulated: true,
      caption: null,
      keywords: null,
      engagements: [],
      events: ["upload", "integrity", "exif", "hash", "attach_time", "derivatives"],
    };
    Object.assign(base, partial);
    list.push(base);
  };

  // Séries de rafales rattachées normalement (shooting 1, voiture 12).
  for (let i = 0; i < 5; i += 1) {
    push({
      id,
      series_id: 900,
      is_series_representative: i === 0,
      engagements: [{ engagement_id: 1, car_number: "12", source: "human", confidence: null }],
    });
    id += 1;
  }

  // Quelques médias isolés bien rattachés à d'autres voitures.
  push({
    id,
    engagements: [{ engagement_id: 3, car_number: "5", source: "human", confidence: null }],
  });
  id += 1;
  push({
    id,
    engagements: [{ engagement_id: 4, car_number: "44", source: "human", confidence: null }],
  });
  id += 1;

  // Bac « à rattacher » : EXIF absent.
  push({
    id,
    shot_at_exif: null,
    shot_at: null,
    ingest_status: "ingested",
    attachment_status: "unattached",
    attachment_source: null,
    attachment_detail: { reason: "no_exif_timestamp" },
    shooting_id: null,
    engagements: [],
    exif: {
      camera_id: null,
      lens_model: null,
      iso: null,
      shutter_speed_sec: null,
      shutter_speed_label: null,
      aperture: null,
      focal_length: null,
      gps_lat: null,
      gps_lon: null,
      exif_raw: null,
    },
  });
  id += 1;

  // Bac « à rattacher » : fenêtre ambiguë entre deux shootings.
  push({
    id,
    shot_at_exif: "2026-06-13T20:15:00",
    shot_at: "2026-06-13T20:15:00Z",
    ingest_status: "ingested",
    attachment_status: "unattached",
    attachment_source: null,
    attachment_detail: { reason: "ambiguous_window", candidate_shooting_ids: [1, 2] },
    shooting_id: null,
    engagements: [],
  });
  id += 1;

  // Quarantaine : fichier tronqué. Clé alignée sur le vrai backend (`pipeline/integrity.py`
  // ::check_integrity, branche décodage tronqué → `{"error": str(exc)}`) — `bytes_read`/
  // `bytes_expected` n'ont jamais existé côté API (§ `implementation.md`, régression déjà
  // trouvée deux fois sur `DETAIL_LABELS`, jamais propagée aux fixtures avant ce lot).
  push({
    id,
    ingest_status: "quarantined",
    quarantine_reason: "truncated_file",
    quarantine_detail: { error: "image file is truncated (12 bytes not processed)" },
    attachment_status: "unattached",
    attachment_source: null,
    shooting_id: null,
    events: ["upload", "integrity"],
  });
  id += 1;

  // Quarantaine : dimensions aberrantes. Clé alignée sur le vrai backend (`expected`, pas
  // `min_expected` — jamais émis par l'API).
  push({
    id,
    width: 40,
    height: 30,
    ingest_status: "quarantined",
    quarantine_reason: "dimensions_out_of_range",
    quarantine_detail: { width: 40, height: 30, expected: "[640..12000]" },
    attachment_status: "unattached",
    attachment_source: null,
    shooting_id: null,
    events: ["upload", "integrity"],
  });
  id += 1;

  // Doublon exact d'un média déjà ingéré (représentant id=1).
  push({
    id,
    duplicate_of_media_id: 1,
    is_series_representative: false,
    series_id: null,
    engagements: [{ engagement_id: 1, car_number: "12", source: "human", confidence: null }],
  });
  id += 1;

  // Bac « à rattacher » : hors plage horaire avec l'horloge actuelle du boîtier — se
  // corrige en réglant le décalage d'horloge de la caméra 2 (démo `/cameras`). Déposée par
  // Awa (id 3, propriétaire de la caméra 2) : illustre la visibilité par déposant tant que
  // le média n'est rattaché à aucun shooting.
  push({
    id,
    uploaded_by: 3,
    shot_at_exif: "2026-05-02T18:05:00",
    shot_at: null,
    ingest_status: "ingested",
    attachment_status: "unattached",
    attachment_source: null,
    // `no_matching_window` (pas `outside_shooting_window`, jamais émis par le backend —
    // même régression déjà corrigée dans `lib/labels.ts`, jamais propagée ici avant ce lot).
    attachment_detail: { reason: "no_matching_window" },
    shooting_id: null,
    engagements: [],
    exif: {
      camera_id: 2,
      lens_model: "Z 70-200mm f/2.8",
      iso: 800,
      shutter_speed_sec: 0.0008,
      shutter_speed_label: "1/1250",
      aperture: 3.2,
      focal_length: 180,
      gps_lat: null,
      gps_lon: null,
      exif_raw: null,
    },
  });
  id += 1;

  // Shooting 3 — sans client au départ, un engagement ajouté après coup.
  push({
    id,
    shooting_id: 3,
    shot_at_exif: "2026-05-02T10:00:00",
    shot_at: "2026-05-02T10:00:00Z",
    batch_id: 1,
    engagements: [{ engagement_id: 7, car_number: "3", source: "human", confidence: null }],
  });
  id += 1;

  // ── J2 — File de validation OCR (§3-J.3) ────────────────────────────────────────────
  // Déjà rattachées au shooting par la fenêtre temporelle (`pipeline_time`), en attente du
  // recoupement OCR humain — `attachment_status='pending_review'`, aucun engagement encore
  // écrit. Numéro lu « 27 » : existe dans la table des engagements du shooting 1
  // (engagement #2) mais confiance entre les deux seuils → suggestion, pas rattachement.
  push({
    id,
    shooting_id: 1,
    shot_at_exif: "2026-06-13T10:40:00",
    shot_at: "2026-06-13T10:40:00Z",
    attachment_status: "pending_review",
    attachment_source: "pipeline_time",
    attachment_detail: null,
    engagements: [],
    exif: {
      camera_id: 1,
      lens_model: "RF 100-500mm F4.5-7.1L",
      iso: 800,
      shutter_speed_sec: 0.0005,
      shutter_speed_label: "1/2000",
      aperture: 5.6,
      focal_length: 320,
      gps_lat: null,
      gps_lon: null,
      exif_raw: null,
    },
  });
  id += 1;
  // Deuxième cas « pas sûr » : numéro lu « 5 » (engagement #3), confiance encore plus faible.
  push({
    id,
    shooting_id: 1,
    shot_at_exif: "2026-06-13T11:05:00",
    shot_at: "2026-06-13T11:05:00Z",
    attachment_status: "pending_review",
    attachment_source: "pipeline_time",
    attachment_detail: null,
    engagements: [],
  });
  id += 1;
  // Cas « sûr mais incohérent » : numéro lu avec une confiance élevée mais absent de la
  // table des engagements du shooting (« 91 » n'existe pas parmi 12/27/5/44) — jamais
  // rattaché de force (§3-J.3, critère d'acceptation explicite).
  push({
    id,
    shooting_id: 1,
    shot_at_exif: "2026-06-13T11:20:00",
    shot_at: "2026-06-13T11:20:00Z",
    attachment_status: "inconsistent",
    attachment_source: "pipeline_time",
    attachment_detail: null,
    engagements: [],
  });
  id += 1;
  // Deuxième incohérence, shooting 2 cette fois (numéro « 71 », absent de 5/9).
  push({
    id,
    shooting_id: 2,
    shot_at_exif: "2026-07-04T09:15:00",
    shot_at: "2026-07-04T09:15:00Z",
    attachment_status: "inconsistent",
    attachment_source: "pipeline_time",
    attachment_detail: null,
    engagements: [],
  });
  id += 1;

  return list;
}

export const media: MediaFixture[] = buildMedia();

export function mediaThumbUrl(item: Pick<MediaOut, "id" | "ingest_status" | "quarantine_reason">): string {
  if (item.ingest_status === "quarantined") {
    return placeholderImage(`Média #${item.id}`, { tone: "#5b1512", sub: item.quarantine_reason ?? "" });
  }
  return placeholderImage(`Média #${item.id}`, { tone: "#1e2434", sub: "Aperçu simulé" });
}

/**
 * Rejoue `MediaSeries.member_count` (backend : compteur tenu à jour par `pipeline/series.py`
 * à l'écriture, pas un `COUNT` recalculé à la volée) — ici un `COUNT` live sur `media` fait
 * l'affaire : le jeu de fixtures est petit et `media` peut grossir en cours de session
 * (upload simulé, `fixtures/batches.ts::uploadFile`), donc un compteur figé au chargement du
 * module dériverait dès le premier upload.
 */
function seriesMemberCount(seriesId: number): number {
  return media.filter((m) => m.series_id === seriesId).length;
}

export function toSummary(item: MediaOut): MediaSummary {
  return {
    id: item.id,
    thumb_url: mediaThumbUrl(item),
    shot_at: item.shot_at,
    ingest_status: item.ingest_status,
    attachment_status: item.attachment_status,
    shooting_id: item.shooting_id,
    is_simulated: item.is_simulated,
    duplicate_of_media_id: item.duplicate_of_media_id,
    series_id: item.series_id,
    series_member_count: item.series_id != null ? seriesMemberCount(item.series_id) : null,
  };
}

/**
 * ── J2 — Réglages OCR (§3-J.2) ────────────────────────────────────────────────────────
 * État mutable (`PUT /settings/ocr` le modifie en place, § `fixtures/settings.ts`) —
 * valeurs par défaut alignées sur `apex/demo/seed.py` (`ocr_high=0.80`, `ocr_low=0.45`).
 */
export const ocrSettings: OcrSettingsOut = {
  high: 0.8,
  low: 0.45,
  min_box_area_ratio: 0.0005,
  max_box_area_ratio: 0.08,
  engine_version: "rapidocr-ppocr-v4-sim",
  updated_at: "2026-08-01T09:00:00Z",
  distribution: { auto: 0, review: 0, abstain: 0, not_engaged: 0 },
};

export type OcrCandidateFixture = OcrCandidateOut & { media_id: number };

/**
 * Candidats bruts persistés (§3-J.4 : « changer les seuils redistribue les cas, sans
 * relancer l'OCR ») — un candidat par média de la file de validation ci-dessus
 * (`buildMedia`, section « J2 »), plus quelques candidats déjà résolus (`accepted`/
 * `rejected`) pour peupler l'historique visible sur `GET /media/{id}/ocr`. `bbox` est
 * désormais le vrai schéma fermé du contrat (`OcrBoundingBox`, `apex.schemas.review`) :
 * `x/y/w/h` **normalisés** `[0..1]` (fraction de l'image), `quad`/`image_width`/
 * `image_height` optionnels — passe d'intégration live J2, voir `implementation.md`.
 */
export const ocrCandidates: OcrCandidateFixture[] = [
  {
    id: 1,
    media_id: 15,
    raw_text: "Z7",
    normalized_number: "27",
    confidence: 0.62,
    bbox: { x: 0.42, y: 0.55, w: 0.16, h: 0.09 },
    engine_version: "rapidocr-ppocr-v4-sim",
    resolution: "review",
    engagement_id: 2,
  },
  {
    id: 2,
    media_id: 16,
    raw_text: "S",
    normalized_number: "5",
    confidence: 0.51,
    bbox: { x: 0.38, y: 0.6, w: 0.1, h: 0.08 },
    engine_version: "rapidocr-ppocr-v4-sim",
    resolution: "review",
    engagement_id: 3,
  },
  {
    id: 3,
    media_id: 17,
    raw_text: "91",
    normalized_number: "91",
    confidence: 0.93,
    bbox: { x: 0.4, y: 0.52, w: 0.18, h: 0.1 },
    engine_version: "rapidocr-ppocr-v4-sim",
    resolution: "not_engaged",
    engagement_id: null,
  },
  {
    id: 4,
    media_id: 18,
    raw_text: "71",
    normalized_number: "71",
    confidence: 0.88,
    bbox: { x: 0.35, y: 0.48, w: 0.17, h: 0.1 },
    engine_version: "rapidocr-ppocr-v4-sim",
    resolution: "not_engaged",
    engagement_id: null,
  },
  // Historique — déjà tranché par un humain avant l'ouverture de la démo, illustre
  // `GET /media/{id}/ocr` sur une fiche média déjà rattachée.
  {
    id: 5,
    media_id: 6,
    raw_text: "5",
    normalized_number: "5",
    confidence: 0.91,
    bbox: { x: 0.44, y: 0.5, w: 0.14, h: 0.09 },
    engine_version: "rapidocr-ppocr-v4-sim",
    resolution: "auto",
    engagement_id: 3,
  },
];

/**
 * ── J2 — Collections ──────────────────────────────────────────────────────────────────
 * `items` porte les `media_id` dans l'ordre de composition (`position`), symétrique au
 * contrat (`CollectionItemOut`). Une collection publiée pour donner une démo J3 non vide.
 */
export const collections: CollectionOut[] = [
  {
    id: 1,
    client_id: 1,
    shooting_id: 1,
    title: "Sélection Roquebrune 6h — voiture #12",
    description: "Meilleurs plans de la rafale principale, à confirmer avec l'écurie.",
    status: "published",
    published_at: "2026-06-14T08:00:00Z",
    created_by: 1,
    items: [
      { media_id: 1, position: 0 },
      { media_id: 2, position: 1 },
      { media_id: 6, position: 2 },
    ],
  },
  {
    id: 2,
    client_id: 2,
    shooting_id: 2,
    title: "Brouillon — championnat régional GT",
    description: null,
    status: "draft",
    published_at: null,
    created_by: 1,
    items: [],
  },
];

