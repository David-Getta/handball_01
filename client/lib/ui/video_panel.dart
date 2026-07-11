/// Jelenet-lejátszó — az elemzett meccs EREDETI videóját játssza le az
/// elemzés mellett. Az Események-listában egy elemre kattintva a lejátszó a
/// jelenet idejére ugrik (a tracking-frame → videó-másodperc átváltást a
/// MatchMeta.videoSecondsOfFrame adja).
///
/// Lokális mód: a videó ugyanazon a gépen van (a feltöltéskor a SportMachine
/// adatmappájába került), ezért közvetlenül fájlból játszjuk le.
/// Platform: macOS/iOS/Android (a video_player csomag támogatása); Windowsra
/// később külön lejátszó kell — addig tájékoztató szöveg jelenik meg.
library;

import "dart:io";

import "package:flutter/material.dart";
import "package:video_player/video_player.dart";

import "../theme/app_theme.dart";

class VideoPanel extends StatefulWidget {
  /// Az eredeti videófájl útja (a Tracking meta.video_path mezőjéből).
  final String videoPath;

  const VideoPanel({super.key, required this.videoPath});

  /// Támogatott-e a beépített videó-lejátszás ezen a platformon.
  static bool get supported =>
      Platform.isMacOS || Platform.isIOS || Platform.isAndroid;

  @override
  State<VideoPanel> createState() => VideoPanelState();
}

class VideoPanelState extends State<VideoPanel> {
  VideoPlayerController? _c;
  String? _error;
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
      final c = VideoPlayerController.file(f);
      await c.initialize();
      if (!mounted) {
        await c.dispose();
        return;
      }
      setState(() => _c = c);
      final pending = _pendingSeekS;
      if (pending != null) {
        _pendingSeekS = null;
        await seekTo(pending);
      }
    } catch (e) {
      if (mounted) setState(() => _error = "A videó nem játszható le: $e");
    }
  }

  /// A megadott másodpercre ugrik, és elindítja a lejátszást.
  Future<void> seekTo(double seconds) async {
    final c = _c;
    if (c == null) {
      _pendingSeekS = seconds; // betöltés után ugrunk
      return;
    }
    final ms = (seconds * 1000).round();
    await c.seekTo(Duration(milliseconds: ms < 0 ? 0 : ms));
    await c.play();
  }

  @override
  void dispose() {
    _c?.dispose();
    super.dispose();
  }

  String _fmt(Duration d) {
    final m = d.inMinutes;
    final s = d.inSeconds % 60;
    return "$m:${s.toString().padLeft(2, '0')}";
  }

  @override
  Widget build(BuildContext context) {
    final c = _c;
    return Container(
      decoration: AppTheme.card(),
      clipBehavior: Clip.antiAlias,
      child: _error != null
          ? Center(
              child: Padding(
                padding: const EdgeInsets.all(AppSpacing.lg),
                child: Text(_error!,
                    style: AppText.label, textAlign: TextAlign.center),
              ),
            )
          : c == null
              ? const Center(child: CircularProgressIndicator())
              : Row(
                  children: [
                    // Maga a videókép (a panel magasságához igazítva).
                    AspectRatio(
                      aspectRatio:
                          c.value.aspectRatio == 0 ? 16 / 9 : c.value.aspectRatio,
                      child: VideoPlayer(c),
                    ),
                    const SizedBox(width: AppSpacing.lg),
                    // Vezérlők: lejátszás/megállítás, ±5 mp, pozíció.
                    Expanded(
                      child: ValueListenableBuilder<VideoPlayerValue>(
                        valueListenable: c,
                        builder: (_, v, __) => Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text("VIDEÓ — JELENET", style: AppText.sectionLabel),
                            const SizedBox(height: AppSpacing.sm),
                            Row(children: [
                              IconButton(
                                onPressed: () => seekTo(
                                    v.position.inMilliseconds / 1000.0 - 5),
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
                                onPressed: () async {
                                  if (v.isPlaying) {
                                    await c.pause();
                                  } else {
                                    await c.play();
                                  }
                                },
                                child: Icon(
                                    v.isPlaying ? Icons.pause : Icons.play_arrow,
                                    size: 22),
                              ),
                              IconButton(
                                onPressed: () => seekTo(
                                    v.position.inMilliseconds / 1000.0 + 5),
                                icon: const Icon(Icons.forward_5,
                                    color: AppColors.textSecondary),
                                tooltip: "5 mp előre",
                              ),
                            ]),
                            const SizedBox(height: AppSpacing.sm),
                            Text(
                              "${_fmt(v.position)} / ${_fmt(v.duration)}",
                              style: AppText.label.copyWith(fontSize: 12),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              "Az Események-listában egy elemre kattintva a "
                              "videó a jelenetre ugrik.",
                              style: AppText.label.copyWith(fontSize: 11),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
    );
  }
}
