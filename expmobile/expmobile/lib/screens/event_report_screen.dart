import 'package:flutter/material.dart';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:image_picker/image_picker.dart';
import '../widgets/app_bottom_menu.dart';

class EventReportScreen extends StatefulWidget {
  const EventReportScreen({super.key});

  @override
  State<EventReportScreen> createState() => _EventReportScreenState();
}

class _EventReportScreenState extends State<EventReportScreen> {
  final _formKey = GlobalKey<FormState>();
  String? selectedDepartment;
  List<String> selectedEventTypes = [];
  List<String> eventCategories = [];
  final TextEditingController locationController = TextEditingController();
  final TextEditingController detailsController = TextEditingController();
  final TextEditingController witnessesController = TextEditingController();
  final ImagePicker _picker = ImagePicker();
  final List<File> selectedImages = [];

  final List<String> departments = ['A', 'B', 'C'];
  final String baseUrl = "https://mainexp-1.onrender.com";

  @override
  void initState() {
    super.initState();
    fetchEventCategories();
  }

  Future<void> fetchEventCategories() async {
    try {
      final response = await http.get(Uri.parse("$baseUrl/api/event-categories"));
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        if (data["success"] == true) {
          setState(() {
            eventCategories = List<String>.from(data["categories"]);
          });
        }
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text("Olay türleri yüklenemedi: $e")),
      );
    }
  }

  Future<void> submitEventReport() async {
    if (!_formKey.currentState!.validate()) return;

    try {
      final response = await http.post(
        Uri.parse("$baseUrl/api/mobile-event-report"),
        headers: {"Content-Type": "application/json"},
        body: json.encode({
          "department": selectedDepartment,
          "event_types": selectedEventTypes,
          "location": locationController.text,
          "details": detailsController.text,
          "witnesses": witnessesController.text,
          "photos": [], // Fotoğraf upload backend'e eklenebilir
        }),
      );

      final data = json.decode(response.body);
      if (response.statusCode == 200 && data["success"] == true) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(data["message"]),
            backgroundColor: Colors.green,
          ),
        );
        _formKey.currentState!.reset();
        setState(() {
          selectedDepartment = null;
          selectedEventTypes.clear();
          selectedImages.clear();
        });
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(data["message"] ?? "Kayıt başarısız"),
            backgroundColor: Colors.red,
          ),
        );
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text("Sunucuya bağlanılamadı: $e"),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  Future<void> pickImages() async {
    final picked = await _picker.pickMultiImage();
    if (picked.isNotEmpty) {
      setState(() {
        selectedImages.addAll(picked.map((x) => File(x.path)));
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text('Olay Bildirimi'),
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
        child: SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: Container(
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.9),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Center(
                      child: Text(
                        'Olay Bildirimi',
                        style: TextStyle(
                          fontSize: 24,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    const SizedBox(height: 25),

                    // Departman
                    const Text('Departman'),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 10,
                      children: departments.map((dept) {
                        return ChoiceChip(
                          label: Text(dept),
                          selected: selectedDepartment == dept,
                          onSelected: (val) =>
                              setState(() => selectedDepartment = dept),
                          selectedColor: const Color(0xFF667EEA),
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 20),

                    // Olay Türü
                    const Text('Olay Türü'),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 10,
                      runSpacing: 10,
                      children: eventCategories.map((type) {
                        final isSelected = selectedEventTypes.contains(type);
                        return FilterChip(
                          label: Text(type),
                          selected: isSelected,
                          onSelected: (val) {
                            setState(() {
                              if (val) {
                                selectedEventTypes.add(type);
                              } else {
                                selectedEventTypes.remove(type);
                              }
                            });
                          },
                          selectedColor: const Color(0xFF764BA2),
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 20),

                    // Olay Yeri
                    TextFormField(
                      controller: locationController,
                      decoration: const InputDecoration(
                        labelText: 'Olay Yeri',
                        hintText: 'Olayın gerçekleştiği yer',
                        border: OutlineInputBorder(),
                      ),
                      validator: (v) =>
                          v!.isEmpty ? 'Olay yerini giriniz' : null,
                    ),
                    const SizedBox(height: 20),

                    // Olay Detayları
                    TextFormField(
                      controller: detailsController,
                      maxLines: 4,
                      decoration: const InputDecoration(
                        labelText: 'Olay Detayları',
                        border: OutlineInputBorder(),
                      ),
                      validator: (v) =>
                          v!.isEmpty ? 'Detayları giriniz' : null,
                    ),
                    const SizedBox(height: 20),

                    // Tanıklar
                    TextFormField(
                      controller: witnessesController,
                      decoration: const InputDecoration(
                        labelText: 'Tanıklar (Varsa)',
                        border: OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 20),

                    // Fotoğraflar
                    const Text('Fotoğraflar (maks. 5)'),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 10,
                      children: [
                        for (var img in selectedImages)
                          Image.file(img,
                              width: 70, height: 70, fit: BoxFit.cover),
                        if (selectedImages.length < 5)
                          GestureDetector(
                            onTap: pickImages,
                            child: Container(
                              width: 70,
                              height: 70,
                              color: Colors.grey[300],
                              child: const Icon(Icons.add),
                            ),
                          )
                      ],
                    ),
                    const SizedBox(height: 30),

                    // Gönder butonu
                    Center(
                      child: ElevatedButton(
                        onPressed: submitEventReport,
                        style: ElevatedButton.styleFrom(
                          padding: EdgeInsets.zero,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(12),
                          ),
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
                            borderRadius:
                                BorderRadius.all(Radius.circular(12)),
                          ),
                          child: Container(
                            alignment: Alignment.center,
                            constraints: const BoxConstraints(
                                minHeight: 50, minWidth: 250),
                            child: const Text(
                              'Olay Raporunu Gönder',
                              style: TextStyle(
                                color: Colors.white,
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ),
                        ),
                      ),
                    )
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
      bottomNavigationBar: const AppBottomMenu(currentIndex: 2),
    );
  }
}
