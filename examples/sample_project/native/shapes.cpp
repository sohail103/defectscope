#include <vector>
#include "util.h"

class Shape {
public:
    virtual double area() const { return 0; }
    int id;
};

class Circle : public Shape {
public:
    double r;
    double area() const override {
        try {
            return 3.14159 * r * r;
        } catch (...) {
            return 0;
        }
    }
    void grow(int d);
};

void Circle::grow(int d) {
    if (d > 0 && r < 100) { r += d; } else if (d < 0 || r > 5) { r -= 1; }
    r = clamp((int)r, 0, 100);
}
