import 'dart:ui';
import 'package:flutter/material.dart';
import 'login_screen.dart';
import '../widgets/app_bottom_menu.dart'; // ✅ ortak alt menü

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final bool isMobile =
        MediaQuery.of(context).size.width < 700; // mobil kontrolü

    return Scaffold(
      extendBodyBehindAppBar: true,
      body: Stack(
        children: [
          // 🌈 Arka plan
          Container(
            decoration: const BoxDecoration(
              gradient: LinearGradient(
                colors: [Color(0xFF667EEA), Color(0xFF764BA2)],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
            ),
          ),

          // 📄 Sayfa içeriği
          Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 60),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(20),
                child: BackdropFilter(
                  filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                  child: Container(
                    width: 600,
                    padding: const EdgeInsets.all(40),
                    decoration: BoxDecoration(
                      color: Colors.white.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(
                        color: Colors.white.withOpacity(0.3),
                      ),
                    ),
                    child: const Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(
                          'İş Sağlığı ve Güvenliği',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 26,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                            shadows: [
                              Shadow(
                                blurRadius: 8,
                                color: Colors.black26,
                                offset: Offset(2, 2),
                              )
                            ],
                          ),
                        ),
                        SizedBox(height: 20),
                        Text(
                          'İş sağlığı ve güvenliği, çalışanların sağlığını korumak ve iş kazalarını önlemek için uygulanan sistemli yaklaşımların bütünüdür. '
                          'Bu sistem, işyerindeki risk faktörlerini belirleyerek, gerekli önlemleri almayı ve çalışanların güvenli bir ortamda çalışmasını sağlamayı hedefler. '
                          'Düzenli eğitimler, risk değerlendirmeleri ve güvenlik raporları ile işyeri güvenliği sürekli olarak izlenir ve iyileştirilir. '
                          'Çalışanların sağlığı ve güvenliği her zaman önceliğimizdir.',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            color: Colors.white70,
                            fontSize: 16,
                            height: 1.5,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),

          // 👤 Profil butonu
          Positioned(
            top: 50,
            right: 20,
            child: GestureDetector(
              onTap: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                    builder: (context) => const LoginScreen(),
                  ),
                );
              },
              child: Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.9),
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.2),
                      blurRadius: 6,
                      offset: const Offset(0, 3),
                    ),
                  ],
                ),
                child: const Icon(
                  Icons.person,
                  color: Color(0xFF667EEA),
                  size: 28,
                ),
              ),
            ),
          ),
        ],
      ),

      // ✅ Ortak alt menü eklendi
      bottomNavigationBar: const AppBottomMenu(currentIndex: 0),
    );
  }
}
