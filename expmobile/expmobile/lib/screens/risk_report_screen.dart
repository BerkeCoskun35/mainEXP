import 'dart:io';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import '../widgets/app_bottom_menu.dart'; // ✅ alt menü import edildi

class RiskReportScreen extends StatefulWidget {
  const RiskReportScreen({super.key});

  @override
  State<RiskReportScreen> createState() => _RiskReportScreenState();
}

class _RiskReportScreenState extends State<RiskReportScreen> {
  final _formKey = GlobalKey<FormState>();

  String? _selectedDepartment;
  List<String> _selectedRisks = [];
  final TextEditingController _detailsController = TextEditingController();
  final TextEditingController _witnessController = TextEditingController();

  final ImagePicker _picker = ImagePicker();
  final List<File> _images = [];

  final List<String> departments = ['A', 'B', 'C'];
  final List<String> riskTypes = [
    'Elektrik Kaçağı',
    'Gaz Sızıntısı',
    'Kaygan Zemin',
    'Madde Sızıntısı'
  ];

  Future<void> _pickImage() async {
    if (_images.length >= 5) return;
    final picked = await _picker.pickImage(source: ImageSource.gallery);
    if (picked != null) {
      setState(() => _images.add(File(picked.path)));
    }
  }

  void _submitReport() {
    if (_formKey.currentState!.validate()) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Rapor başarıyla gönderildi!'),
          backgroundColor: Colors.green,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text('Risk Bildirimi'),
        backgroundColor: Colors.transparent,
        elevation: 0,
        centerTitle: true,
      ),
      body: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            colors: [Color(0xFF667EEA), Color(0xFF764BA2)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
        ),
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: Container(
              width: 700,
              padding: const EdgeInsets.all(30),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.95),
                borderRadius: BorderRadius.circular(20),
                boxShadow: const [
                  BoxShadow(
                    color: Colors.black26,
                    blurRadius: 25,
                    offset: Offset(0, 8),
                  ),
                ],
              ),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      '',
                      style: TextStyle(
                        fontSize: 26,
                        fontWeight: FontWeight.bold,
                        color: Color(0xFF333333),
                      ),
                    ),
                    const SizedBox(height: 8),
                    const Text(
                      'Gözlemlediğiniz riski detaylarıyla birlikte hızlıca bildirin.',
                      style: TextStyle(
                        color: Colors.black54,
                        fontSize: 15,
                      ),
                    ),
                    const SizedBox(height: 30),

                    // Departman seçimi
                    const Text(
                      'Departman',
                      style:
                          TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 10,
                      children: departments.map((dept) {
                        final selected = _selectedDepartment == dept;
                        return ChoiceChip(
                          label: Text(dept),
                          selected: selected,
                          onSelected: (_) =>
                              setState(() => _selectedDepartment = dept),
                          selectedColor: const Color(0xFF667EEA),
                          labelStyle: TextStyle(
                            color: selected ? Colors.white : Colors.black87,
                          ),
                          backgroundColor: Colors.grey[200],
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 20),

                    // Risk Türü
                    const Text(
                      'Risk Türü',
                      style:
                          TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 10,
                      runSpacing: 10,
                      children: riskTypes.map((risk) {
                        final selected = _selectedRisks.contains(risk);
                        return FilterChip(
                          label: Text(risk),
                          selected: selected,
                          onSelected: (value) {
                            setState(() {
                              if (value) {
                                _selectedRisks.add(risk);
                              } else {
                                _selectedRisks.remove(risk);
                              }
                            });
                          },
                          selectedColor: const Color(0xFF764BA2),
                          labelStyle: TextStyle(
                            color: selected ? Colors.white : Colors.black87,
                          ),
                          backgroundColor: Colors.grey[200],
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 30),

                    // Detaylar
                    const Text(
                      'Detaylar',
                      style:
                          TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: _detailsController,
                      maxLines: 5,
                      decoration: InputDecoration(
                        hintText:
                            'Riskin konumu, durumu, alınan önlemler vb. detayları yazın...',
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                      validator: (v) =>
                          v!.isEmpty ? 'Lütfen detayları giriniz' : null,
                    ),
                    const SizedBox(height: 20),

                    // Tanıklar
                    const Text(
                      'Tanıklar (Varsa)',
                      style:
                          TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 10),
                    TextFormField(
                      controller: _witnessController,
                      decoration: InputDecoration(
                        hintText:
                            'Risk durumunu gören kişilerin isimlerini yazın...',
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                    ),
                    const SizedBox(height: 20),

                    // Fotoğraflar
                    const Text(
                      'Fotoğraflar (maks. 5)',
                      style:
                          TextStyle(fontSize: 18, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 10,
                      children: [
                        for (var img in _images)
                          Stack(
                            children: [
                              Image.file(img,
                                  width: 80, height: 80, fit: BoxFit.cover),
                              Positioned(
                                right: 0,
                                top: 0,
                                child: GestureDetector(
                                  onTap: () =>
                                      setState(() => _images.remove(img)),
                                  child: Container(
                                    color: Colors.black54,
                                    child: const Icon(Icons.close,
                                        color: Colors.white, size: 18),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        if (_images.length < 5)
                          GestureDetector(
                            onTap: _pickImage,
                            child: Container(
                              width: 80,
                              height: 80,
                              decoration: BoxDecoration(
                                color: Colors.white,
                                border: Border.all(
                                  color: const Color(0xFF667EEA),
                                  width: 2,
                                ),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: const Icon(Icons.add,
                                  color: Color(0xFF667EEA), size: 28),
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 30),

                    // Raporu Gönder Butonu
                    ElevatedButton(
                      onPressed: _submitReport,
                      style: ElevatedButton.styleFrom(
                        padding: EdgeInsets.zero,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                        elevation: 5,
                        backgroundColor: Colors.transparent,
                        shadowColor: Colors.transparent,
                      ),
                      child: Ink(
                        decoration: const BoxDecoration(
                          gradient: LinearGradient(
                            colors: [Color(0xFF667EEA), Color(0xFF764BA2)],
                            begin: Alignment.centerLeft,
                            end: Alignment.centerRight,
                          ),
                          borderRadius: BorderRadius.all(Radius.circular(12)),
                        ),
                        child: Container(
                          alignment: Alignment.center,
                          constraints:
                              const BoxConstraints(minHeight: 50, minWidth: 200),
                          child: const Text(
                            'Raporu Gönder',
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 18,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),

      // ✅ Sadece AppBottomMenu kaldı
      bottomNavigationBar: const AppBottomMenu(currentIndex: 1),
    );
  }
}
