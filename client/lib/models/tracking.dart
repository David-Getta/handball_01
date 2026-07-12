/// A Tracking adatmodell DART-megfelelője — a backend JSON-jának tükre.
///
/// A backend (Python, handball.models.tracking) JSON-t ad; ezek az osztályok azt
/// olvassák be 1:1-ben. A mezőnevek a JSON kulcsaival egyeznek (snake_case).
/// Így a kliens pontosan azt jeleníti meg, amit a backend előállít.
library;

/// Melyik csapat. A JSON-ban "home"/"away" szövegként szerepel.
enum Team { home, away }

Team _teamFromString(String s) => s == "away" ? Team.away : Team.home;

/// A pozíció forrása: a kamera látta (measured) vagy becsült (estimated).
/// A becsült játékost a megjelenítés halványítva mutatja.
enum PositionSource { measured, estimated }

PositionSource _sourceFromString(String s) =>
    s == "estimated" ? PositionSource.estimated : PositionSource.measured;

/// Egy játékos egy frame-en, pálya-koordinátán (méter).
class PlayerPosition {
  final int trackId;
  final Team team;
  final double x; // méter, a 40 m-es hossz mentén
  final double y; // méter, a 20 m-es szélesség mentén
  final PositionSource source;
  final double confidence;
  // Módosítható: a kézi mezszám-hozzárendelés (és később az OCR) a betöltött
  // meccsen is átírja, hogy minden nézet azonnal a számot mutassa.
  int? jerseyNumber;
  final String? role;

  PlayerPosition({
    required this.trackId,
    required this.team,
    required this.x,
    required this.y,
    required this.source,
    required this.confidence,
    this.jerseyNumber,
    this.role,
  });

  bool get isEstimated => source == PositionSource.estimated;

  factory PlayerPosition.fromJson(Map<String, dynamic> j) => PlayerPosition(
        trackId: (j["track_id"] as num).toInt(),
        team: _teamFromString(j["team"] as String),
        x: (j["x"] as num).toDouble(),
        y: (j["y"] as num).toDouble(),
        source: _sourceFromString((j["source"] ?? "measured") as String),
        confidence: (j["confidence"] as num?)?.toDouble() ?? 1.0,
        jerseyNumber: (j["jersey_number"] as num?)?.toInt(),
        role: j["role"] as String?,
      );
}

/// A labda pozíciója egy frame-en (méter), vagy null, ha nem ismert.
class Ball {
  final double x;
  final double y;
  final double confidence;

  Ball({required this.x, required this.y, required this.confidence});

  factory Ball.fromJson(Map<String, dynamic> j) => Ball(
        x: (j["x"] as num).toDouble(),
        y: (j["y"] as num).toDouble(),
        confidence: (j["confidence"] as num?)?.toDouble() ?? 1.0,
      );
}

/// A meccs egy időpillanata (egy feldolgozott képkocka).
class Frame {
  final int t; // idő (frame-index)
  final List<PlayerPosition> players;
  final Ball? ball;

  Frame({required this.t, required this.players, this.ball});

  factory Frame.fromJson(Map<String, dynamic> j) => Frame(
        t: (j["t"] as num).toInt(),
        players: (j["players"] as List<dynamic>)
            .map((p) => PlayerPosition.fromJson(p as Map<String, dynamic>))
            .toList(),
        ball: j["ball"] == null
            ? null
            : Ball.fromJson(j["ball"] as Map<String, dynamic>),
      );
}

/// A meccs fejléc-adatai.
class MatchMeta {
  final String matchId;
  final String homeTeam;
  final String awayTeam;
  final double fps;
  final int frameWidth;
  final int frameHeight;
  final String? date;

  /// Az eredeti videófájl útja a gépen (lokális mód) — a jelenet-lejátszáshoz.
  final String? videoPath;

  /// A feldolgozás első kép-indexe + mintavétel az eredeti videóban.
  final int startFrame;
  final int stride;

  MatchMeta({
    required this.matchId,
    required this.homeTeam,
    required this.awayTeam,
    required this.fps,
    required this.frameWidth,
    required this.frameHeight,
    this.date,
    this.videoPath,
    this.startFrame = 0,
    this.stride = 1,
  });

  factory MatchMeta.fromJson(Map<String, dynamic> j) => MatchMeta(
        matchId: j["match_id"] as String,
        homeTeam: j["home_team"] as String,
        awayTeam: j["away_team"] as String,
        fps: (j["fps"] as num).toDouble(),
        frameWidth: (j["frame_width"] as num?)?.toInt() ?? 0,
        frameHeight: (j["frame_height"] as num?)?.toInt() ?? 0,
        date: j["date"] as String?,
        videoPath: j["video_path"] as String?,
        startFrame: (j["start_frame"] as num?)?.toInt() ?? 0,
        stride: (j["stride"] as num?)?.toInt() ?? 1,
      );

  /// Az i. tracking-frame ideje az EREDETI videóban, másodpercben.
  /// (Az fps a tracking képrátája: az eredeti videóé osztva a stride-dal.)
  double videoSecondsOfFrame(int i) {
    if (fps <= 0) return 0;
    return startFrame / (fps * stride) + i / fps;
  }
}

/// A teljes Tracking: fejléc + minden frame. Ezt rajzolja ki a kliens.
class Match {
  final MatchMeta meta;
  final List<Frame> frames;

  Match({required this.meta, required this.frames});

  factory Match.fromJson(Map<String, dynamic> j) => Match(
        meta: MatchMeta.fromJson(j["meta"] as Map<String, dynamic>),
        frames: (j["frames"] as List<dynamic>)
            .map((f) => Frame.fromJson(f as Map<String, dynamic>))
            .toList(),
      );
}
