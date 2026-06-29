/// A Flutter-kliens belépési pontja (desktop-first).
///
/// Ugyanaz a kódbázis fut Windows/Mac/Linux desktopon és tableten (iPad/Android).
/// Indítás (asztali, lokális teszt): `flutter run -d windows` (vagy macos/linux).
/// Lásd client/README.md.
library;

import "package:flutter/material.dart";

import "ui/match_screen.dart";

void main() {
  runApp(const HandballApp());
}

class HandballApp extends StatelessWidget {
  const HandballApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: "Kézilabda elemző",
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF1E66F5)),
        useMaterial3: true,
      ),
      home: const MatchScreen(),
    );
  }
}
