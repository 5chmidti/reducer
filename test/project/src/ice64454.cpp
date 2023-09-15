template<class> struct Q {
  auto f(auto r) requires (r());
};
template <class T>
  auto Q<T>::f(auto r) requires (r()) { }
struct True {
  consteval bool operator()() { return true; }
};
int main() {
  Q<int>{}.f(True{});
}
