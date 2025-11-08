import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'dart:convert';
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
      final response = await http.get(Uri.parse('$baseUrl/api/mobile-event-categories'));
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

  Future<void> _pickImage() async {
    final picked = await _picker.pickImage(source: ImageSource.gallery);
    if (picked != null) {
      setState(() {
        if (selectedImages.length < 5) {
          selectedImages.add(File(picked.path));
        }
      });
    }
  }

  Future<void> _submitReport() async {
    if (!_formKey.currentState!.validate()) return;

    try {
      final response = await http.post(
        Uri.parse('$baseUrl/api/mobile-event-report'),
        headers: {"Content-Type": "application/json"},
        body: json.encode({
          "department": selectedDepartment,
          "event_types": selectedEventTypes,
          "location": locationController.text,
          "details": detailsController.text,
          "witnesses": witnessesController.text,
        }),
      );

      final data = json.decode(response.body);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(data["message"] ?? "Rapor gönderildi."),
          backgroundColor: data["success"] == true ? Colors.green : Colors.red,
        ),
      );

      if (data["success"] == true) {
        setState(() {
          selectedDepartment = null;
          selectedEventTypes.clear();
          locationController.clear();
          detailsController.clear();
          witnessesController.clear();
          selectedImages.clear();
        });
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text("Sunucu hatası: $e")),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBodyBehindAppBar: true,
      appBar: AppBar(
        title: const Text("Olay Bildirimi", style: TextStyle(color: Colors.white)),
        backgroundColor: Colors.transparent,
        elevation: 0,
      ),
      bottomNavigationBar: const AppBottomMenu(currentIndex: 2),
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
              width: 380,
              padding: const EdgeInsets.all(20),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.9),
                borderRadius: BorderRadius.circular(20),
                boxShadow: const [
                  BoxShadow(color: Colors.black26, blurRadius: 15, offset: Offset(0, 6)),
                ],
              ),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Center(
                      child: Text(
                        "Olay Bildirimi",
                        style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
                      ),
                    ),
                    const SizedBox(height: 20),

                    // Departman
                    const Text("Departman", style: TextStyle(fontWeight: FontWeight.w600)),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 10,
                      children: departments.map((dept) {
                        return ChoiceChip(
                          label: Text(dept),
                          selected: selectedDepartment == dept,
                          onSelected: (_) => setState(() => selectedDepartment = dept),
                          selectedColor: Colors.indigo,
                          labelStyle: TextStyle(
                            color: selectedDepartment == dept ? Colors.white : Colors.black,
                          ),
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 20),

                    // Olay Türü
                    const Text("Olay Türü", style: TextStyle(fontWeight: FontWeight.w600)),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 10,
                      runSpacing: 8,
                      children: eventCategories.map((type) {
                        return FilterChip(
                          label: Text(type),
                          selected: selectedEventTypes.contains(type),
                          onSelected: (isSelected) {
                            setState(() {
                              isSelected
                                  ? selectedEventTypes.add(type)
                                  : selectedEventTypes.remove(type);
                            });
                          },
                          selectedColor: Colors.indigo,
                          labelStyle: TextStyle(
                            color: selectedEventTypes.contains(type)
                                ? Colors.white
                                : Colors.black,
                          ),
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 20),

                    // Olay Yeri
                    TextFormField(
                      controller: locationController,
                      decoration: const InputDecoration(
                        labelText: "Olay Yeri",
                        border: OutlineInputBorder(),
                      ),
                      validator: (v) =>
                          v == null || v.isEmpty ? "Olay yerini giriniz" : null,
                    ),
                    const SizedBox(height: 15),

                    // Olay Detayları
                    TextFormField(
                      controller: detailsController,
                      maxLines: 3,
                      decoration: const InputDecoration(
                        labelText: "Olay Detayları",
                        border: OutlineInputBorder(),
                      ),
                      validator: (v) =>
                          v == null || v.isEmpty ? "Olay detaylarını giriniz" : null,
                    ),
                    const SizedBox(height: 15),

                    // Tanıklar
                    TextFormField(
                      controller: witnessesController,
                      decoration: const InputDecoration(
                        labelText: "Tanıklar (Varsa)",
                        border: OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 20),

                    // Fotoğraflar
                    const Text("Fotoğraflar (maks. 5)",
                        style: TextStyle(fontWeight: FontWeight.w600)),
                    const SizedBox(height: 10),
                    Wrap(
                      spacing: 8,
                      children: [
                        ...selectedImages.map((img) => Image.file(img, width: 60, height: 60)),
                        if (selectedImages.length < 5)
                          GestureDetector(
                            onTap: _pickImage,
                            child: Container(
                              width: 60,
                              height: 60,
                              decoration: BoxDecoration(
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(color: Colors.grey),
                              ),
                              child: const Icon(Icons.add),
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 30),

                    // Gönder Butonu
                    ElevatedButton(
                      onPressed: _submitReport,
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
                          borderRadius: BorderRadius.all(Radius.circular(12)),
                        ),
                        child: Container(
                          alignment: Alignment.center,
                          padding: const EdgeInsets.symmetric(vertical: 15),
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
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
