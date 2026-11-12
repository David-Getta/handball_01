/// Jelenet-lejátszó — az elemzett meccs EREDETI videóját játssza le az
/// elemzés mellett. Az Események-listában egy elemre kattintva a lejátszó a
/// jelenet idejére ugrik (a tracking-frame → videó-másodperc átváltást a
/// MatchMeta.videoSecondsOfFrame adja).
///
/// Lokális mód: a videó ugyanazon a gépen van (a feltöltéskor a SportMachine
/// adatmappájába került), ezért közvetlenül fájlból játszjuk le.
/// Platform: macOS/iOS/Android a video_player csomaggal; Windows a
/// media_kit (libmpv) lejátszóval — ott a video_player nem támogatott.
library;

import "dart:io";

import "package:flutter/material.dart";
import "package:media_kit/media_kit.dart" as mk;
import "package:media_kit_video/media_kit_video.dart" as mkv;
import "package:video_player/video_player.dart";

import "../theme/app_theme.dart";
import "error_text.dart";
import "waiting.dart";
import "zoomable.dart";

class VideoPanel extends StatefulWidget {
  /// Az eredeti videófájl útja (a Tracking meta.video_path mezőjéből).
  final String videoPath;

  /// A vezérlők alatti súgó-sor (a meccs-nézetben az Események-lista
  /// kattintására utal; máshol más a használat).
  final String hint;

  /// Látszódjanak-e a videókép sarkában a nagyítás-gombok (+ / − / 1×).
  final bool zoomButtons;

  /// Betöltés után ide áll (másodperc), lejátszás NÉLKÜL — pl. a kézi
  /// elemzés a meccs-nézet idejéről nyílik.
  final double? initialSeconds;

  const VideoPanel({
    super.key,
    required this.videoPath,
    this.hint = "Az Események-listában egy elemre kattintva a "
        "videó a jelenetre ugrik.",
    this.zoomButtons = false,
    this.initialSeconds,
  });

  /// Támogatott-e a beépített videó-lejátszás ezen a platformon.
  static bool get supported =>
      Platform.isMacOS || Platform.isIOS || Platform.isAndroid ||
      Platform.isWindows;

  /// Windowson a media_kit (libmpv) játszik le; máshol a video_player.
  static bool get _useMediaKit => Platform.isWindows;

  @override
  State<VideoPanel> createState() => VideoPanelState();
}

class VideoPanelState extends State<VideoPanel> {
  VideoPlayerController? _c;
  mk.Player? _mk;
  mkv.VideoController? _mkView;
  String? _error;
  /// A választható lejátszási sebességek (elemzéshez a lassítás kell).
  static const List<double> speeds = [0.25, 0.5, 1.0, 1.5, 2.0];
  double _speed = 1.0;

  // Ha a seek a betöltés BEFEJEZÉSE előtt érkezik (pl. eseményre kattintva
  // nyílt meg a panel), eltesszük, és betöltés után ugrunk oda.
  double? _pendingSeekS;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    if (!VideoPanel.supported) {
      setState(() => _error =
          "A beépített videó-lejátszás ezen a platformon még nem érhető el.");
      return;
    }
    try {
      final f = File(widget.videoPath);
      if (!f.existsSync()) {
        setState(() => _error =
            "A videófájl nem található:\n${widget.videoPath}\n"
            "(Másik gépen készült az elemzés, vagy törölted a videót.)");
        return;
      }
      if (VideoPanel._useMediaKit) {
        final p = mk.Player();
        final view = mkv.VideoController(p);
        await p.open(mk.Media(widget.videoPath), play: false);
        if (!mounted) {
          await p.dispose();
          return;
        }
        setState(() {
          _mk = p;
          _mkView = view;
        });
      } else {
        final c = VideoPlayerController.file(f);
        await c.initialize();
        if (!mounted) {
          await c.dispose();
          return;
        }
        setState(() => _c = c);
      }
      final pending = _pendingSeekS;
      final initial = widget.initialSeconds;
      if (pending != null) {
        _pendingSeekS = null;
        await seekTo(pending);
      } else if (initial != null && initial > 0) {
        await seekTo(initial, play: false);
      }
    } catch (e) {
      if (mounted) setState(() => _error = "A videó nem játszható le: ${humanError(e)}");
    }
  }

  /// A megadott másodpercre ugrik, és (alapból) elindítja a lejátszást.
  Future<void> seekTo(double seconds, {bool play = true}) async {
    final ms = (seconds * 1000).round();
    final d = Duration(milliseconds: ms < 0 ? 0 : ms);
    final p = _mk;
    if (p != null) {
      await p.seek(d);
      if (play) await p.play();
      return;
    }
    final c = _c;
    if (c == null) {
      _pendingSeekS = seconds; // betöltés után ugrunk
      return;
    }
    await c.seekTo(d);
    if (play) await c.play();
  }

  /// Megy-e most a lejátszás.
  bool get isPlaying {
    final p = _mk;
    if (p != null) return p.state.playing;
    final c = _c;
    return c != null && c.value.isInitialized && c.value.isPlaying;
  }

  /// Lejátszás / szünet váltása (billentyűről is).
  Future<void> togglePlay() async {
    final p = _mk;
    if (p != null) {
      await p.playOrPause();
      return;
    }
    final c = _c;
    if (c == null || !c.value.isInitialized) return;
    if (c.value.isPlaying) {
      await c.pause();
    } else {
      await c.play();
    }
  }

  /// Ugrás a mostani helyhez képest (a lejátszás állapota marad).
  Future<void> seekBy(double deltaS) async {
    final now = positionSeconds;
    if (now == null) return;
    final t = now + deltaS;
    await seekTo(t < 0 ? 0 : t, play: isPlaying);
  }

  /// Lejátszási sebesség (0,25× … 2×).
  Future<void> setSpeed(double v) async {
    setState(() => _speed = v);
    final p = _mk;
    if (p != null) {
      await p.setRate(v);
      return;
    }
    final c = _c;
    if (c != null && c.value.isInitialized) await c.setPlaybackSpeed(v);
  }

  static String _speedLabel(double v) =>
      "${v == v.roundToDouble() ? v.toInt() : v.toString().replaceAll(".", ",")}×";

  Widget _speedButton() {
    return PopupMenuButton<double>(
      tooltip: "Lejátszási sebesség",
      initialValue: _speed,
      onSelected: setSpeed,
      itemBuilder: (_) => [
        for (final v in speeds)
          PopupMenuItem<double>(value: v, child: Text(_speedLabel(v))),
      ],
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
              color: _speed == 1.0 ? AppColors.border : AppColors.accent),
        ),
        child: Text(_speedLabel(_speed),
            style: AppText.label.copyWith(
                fontSize: 12,
                color: _speed == 1.0 ? null : AppColors.accent)),
      ),
    );
  }

  /// A lejátszó aktuális helye (másodperc) — null, amíg nem töltött be.
  double? get positionSeconds {
    final p = _mk;
    if (p != null) return p.state.position.inMilliseconds / 1000.0;
    final c = _c;
    if (c == null || !c.value.isInitialized) return null;
    return c.value.position.inMilliseconds / 1000.0;
  }

  @override
  void dispose() {
    _c?.dispose();
    _mk?.dispose();
    super.dispose();
  }

  String _fmt(Duration d) {
    final m = d.inMinutes;
    final s = d.inSeconds % 60;
    return "$m:${s.toString().padLeft(2, '0')}";
  }

  /// Vezérlő-oszlop (cím, lejátszás/±5 mp, pozíció) — a két lejátszó
  /// közös felülete; csak az állapot-források különböznek.
  Widget _controls({
    required bool playing,
    required Duration position,
    required Duration duration,
    required Future<void> Function() onToggle,
    bool compact = false,
  }) {
    if (compact) {
      // Keskeny/magas helyen a vezérlő egyetlen sor a kép ALATT.
      return Row(children: [
        IconButton(
          onPressed: () => seekTo(position.inMilliseconds / 1000.0 - 5),
          icon: const Icon(Icons.replay_5, color: AppColors.textSecondary),
          tooltip: "5 mp vissza",
        ),
        IconButton(
          onPressed: onToggle,
          icon: Icon(playing ? Icons.pause_circle : Icons.play_circle,
              color: AppColors.accent, size: 28),
          tooltip: playing ? "Szünet" : "Lejátszás",
        ),
        IconButton(
          onPressed: () => seekTo(position.inMilliseconds / 1000.0 + 5),
          icon: const Icon(Icons.forward_5, color: AppColors.textSecondary),
          tooltip: "5 mp előre",
        ),
        const SizedBox(width: AppSpacing.sm),
        Text("${_fmt(position)} / ${_fmt(duration)}",
            style: AppText.label.copyWith(fontSize: 12)),
        const SizedBox(width: AppSpacing.sm),
        _speedButton(),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Text(widget.hint,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: AppText.label.copyWith(fontSize: 11)),
        ),
      ]);
    }
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text("VIDEÓ — JELENET", style: AppText.sectionLabel),
        const SizedBox(height: AppSpacing.sm),
        Row(children: [
          IconButton(
            onPressed: () =>
                seekTo(position.inMilliseconds / 1000.0 - 5),
            icon: const Icon(Icons.replay_5,
                color: AppColors.textSecondary),
            tooltip: "5 mp vissza",
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: AppColors.accent,
              foregroundColor: AppColors.onAccent,
              shape: const CircleBorder(),
              padding: const EdgeInsets.all(10),
            ),
            onPressed: onToggle,
            child: Icon(playing ? Icons.pause : Icons.play_arrow,
                size: 22),
          ),
          IconButton(
            onPressed: () =>
                seekTo(position.inMilliseconds / 1000.0 + 5),
            icon: const Icon(Icons.forward_5,
                color: AppColors.textSecondary),
            tooltip: "5 mp előre",
          ),
          const SizedBox(width: AppSpacing.sm),
          _speedButton(),
        ]),
        const SizedBox(height: AppSpacing.sm),
        Text(
          "${_fmt(position)} / ${_fmt(duration)}",
          style: AppText.label.copyWith(fontSize: 12),
        ),
        const SizedBox(height: 4),
        Text(widget.hint, style: AppText.label.copyWith(fontSize: 11)),
      ],
    );
  }

  /// A kép + vezérlők elrendezése. Széles, lapos helyen (a meccs-nézet
  /// sávja) a vezérlő a kép MELLETT áll; ha a hely inkább magas (a kézi
  /// elemzés videó-sávja, keskeny ablak), a kép kitölti a helyet, és a
  /// vezérlő egy sor ALATTA — így a kép a lehető legnagyobb.
  Widget _layout(double aspect, Widget video,
      Widget Function(bool compact) controls) {
    final zoomable = AspectRatio(
      aspectRatio: aspect,
      // Nagyítható: csippentés (MacBook touchpad is), Ctrl/⌘+görgő,
      // vagy a sarok-gombok.
      child: ZoomPanView(showButtons: widget.zoomButtons, child: video),
    );
    return LayoutBuilder(builder: (ctx, cons) {
      final sideBySide = cons.maxWidth >= cons.maxHeight * aspect + 260;
      if (sideBySide) {
        return Row(children: [
          zoomable,
          const SizedBox(width: AppSpacing.lg),
          Expanded(child: controls(false)),
        ]);
      }
      return Column(children: [
        Expanded(child: Center(child: zoomable)),
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
          child: controls(true),
        ),
      ]);
    });
  }

  /// A media_kit (Windows) lejátszó felülete.
  Widget _mediaKitBody(mk.Player p, mkv.VideoController view) {
    final w = p.state.width ?? 16;
    final h = p.state.height ?? 9;
    return _layout(
      h == 0 ? 16 / 9 : w / h,
      mkv.Video(controller: view, controls: mkv.NoVideoControls),
      // Vezérlők: a lejátszó állapot-folyamaiból frissülnek.
      (compact) => StreamBuilder<bool>(
        stream: p.stream.playing,
        initialData: p.state.playing,
        builder: (_, playing) => StreamBuilder<Duration>(
          stream: p.stream.position,
          initialData: p.state.position,
          builder: (_, pos) => _controls(
            playing: playing.data ?? false,
            position: pos.data ?? Duration.zero,
            duration: p.state.duration,
            onToggle: () => p.playOrPause(),
            compact: compact,
          ),
        ),
      ),
    );
  }

  /// A video_player (macOS/iOS/Android) lejátszó felülete.
  Widget _videoPlayerBody(VideoPlayerController c) {
    return _layout(
      c.value.aspectRatio == 0 ? 16 / 9 : c.value.aspectRatio,
      VideoPlayer(c),
      (compact) => ValueListenableBuilder<VideoPlayerValue>(
        valueListenable: c,
        builder: (_, v, __) => _controls(
          playing: v.isPlaying,
          position: v.position,
          duration: v.duration,
          onToggle: () async {
            if (v.isPlaying) {
              await c.pause();
            } else {
              await c.play();
            }
          },
          compact: compact,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final c = _c;
    final p = _mk;
    final view = _mkView;
    Widget body;
    if (_error != null) {
      body = Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Text(_error!,
              style: AppText.label, textAlign: TextAlign.center),
        ),
      );
    } else if (p != null && view != null) {
      body = _mediaKitBody(p, view);
    } else if (c != null) {
      body = _videoPlayerBody(c);
    } else {
      body = const WaitingView("Videókép betöltése…",
          hint: "Az első képkocka kiolvasása a felvételből.",
          icon: Icons.movie_outlined);
    }
    return Container(
      decoration: AppTheme.card(),
      clipBehavior: Clip.antiAlias,
      child: body,
    );
  }
}
