import 'package:flutter/material.dart';

class AppBottomMenu extends StatelessWidget {
  final int currentIndex;
  const AppBottomMenu({super.key, required this.currentIndex});

  void _onItemTapped(BuildContext context, int index) {
    if (index == currentIndex) return;

    switch (index) {
      case 0:
        Navigator.pushReplacementNamed(context, '/home');
        break;
      case 1:
        Navigator.pushReplacementNamed(context, '/risk-report');
        break;
      case 2:
        Navigator.pushReplacementNamed(context, '/event-report'); // ✅ Yeni rota
        break;
      case 3:
        Navigator.pushReplacementNamed(context, '/profile');
        break;
    }
  }

  @override
  Widget build(BuildContext context) {
    return BottomNavigationBar(
      type: BottomNavigationBarType.fixed, // 4 sekme için gerekli
      currentIndex: currentIndex,
      onTap: (index) => _onItemTapped(context, index),
      selectedItemColor: Colors.redAccent,
      unselectedItemColor: Colors.grey,
      items: const [
        BottomNavigationBarItem(
          icon: Icon(Icons.home),
          label: 'Ana Sayfa',
        ),
        BottomNavigationBarItem(
          icon: Icon(Icons.report_problem),
          label: 'Risk Bildir',
        ),
        BottomNavigationBarItem(
          icon: Icon(Icons.warning_amber_rounded), // ⚠️ Olay bildir simgesi
          label: 'Olay Bildir',
        ),
        BottomNavigationBarItem(
          icon: Icon(Icons.person),
          label: 'Profil',
        ),
      ],
    );
  }
}
